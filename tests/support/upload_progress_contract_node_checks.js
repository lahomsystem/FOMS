const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const root = path.resolve(__dirname, '..', '..');
const source = fs.readFileSync(path.join(root, 'static/js/runtime/upload-progress.js'), 'utf8');

class MockFile {
  constructor(parts, name, options) {
    this.parts = parts || [];
    this.name = name;
    this.type = (options && options.type) || '';
    this.lastModified = (options && options.lastModified) || Date.now();
    this.size = this.parts.reduce((total, part) => total + (part.size || String(part).length || 0), 0);
  }
}

function makeContext(options = {}) {
  let lastCanvas = null;
  let xhrIndex = 0;
  const context = {
    console,
    Promise,
    Blob,
    File: MockFile,
    Image: function MockImage() {},
    setTimeout,
    clearTimeout,
    XMLHttpRequest: function MockXMLHttpRequest() {
      const listeners = {};
      this.upload = { addEventListener() {} };
      this.addEventListener = (event, cb) => {
        listeners[event] = cb;
      };
      this.open = () => {};
      this.send = () => {
        if (typeof options.onXhrSend === 'function') options.onXhrSend();
        const responses = options.xhrResponses || [{ status: 200, body: { success: true } }];
        const response = responses[Math.min(xhrIndex, responses.length - 1)];
        xhrIndex += 1;
        setTimeout(() => {
          if (response.error) {
            if (listeners.error) listeners.error();
            return;
          }
          this.status = response.status || 200;
          this.responseText = JSON.stringify(response.body || {});
          if (listeners.load) listeners.load();
        }, 0);
      };
    },
    fetch: options.fetch || (async () => ({ json: async () => ({ success: true }) })),
    FormData: class MockFormData {
      constructor() {
        this.fields = [];
      }

      append(key, value) {
        this.fields.push([key, value]);
      }
    },
  };
  context.window = context;
  context.window.matchMedia = () => ({ matches: !!options.coarsePointer });
  context.window.requestAnimationFrame = (cb) => setTimeout(cb, 0);
  context.window.URL = {
    createObjectURL: () => 'blob:mock',
    revokeObjectURL: () => {},
  };
  context.window.createImageBitmap = async (file) => ({
    width: file.mockWidth || 4000,
    height: file.mockHeight || 2000,
    closeCalled: false,
    close() { this.closeCalled = true; },
  });
  context.document = {
    createElement(tag) {
      assert.strictEqual(tag, 'canvas');
      const canvas = {
        widthHistory: [],
        heightHistory: [],
        drawArgs: null,
        getContext() {
          return {
            drawImage: (...args) => {
              canvas.drawArgs = args;
            },
          };
        },
        toBlob(cb, type, quality) {
          canvas.toBlobType = type;
          canvas.toBlobQuality = quality;
          const blobType = options.blobType || type;
          setTimeout(() => cb(new Blob(['small'], { type: blobType })), 0);
        },
      };
      let widthValue = 0;
      let heightValue = 0;
      Object.defineProperty(canvas, 'width', {
        get() { return widthValue; },
        set(value) {
          widthValue = value;
          canvas.widthHistory.push(value);
        },
      });
      Object.defineProperty(canvas, 'height', {
        get() { return heightValue; },
        set(value) {
          heightValue = value;
          canvas.heightHistory.push(value);
        },
      });
      lastCanvas = canvas;
      return canvas;
    },
  };
  vm.createContext(context);
  vm.runInContext(source, context, { filename: 'upload-progress.js' });
  context.getLastCanvas = () => lastCanvas;
  return context;
}

async function run() {
  {
    const ctx = makeContext({ coarsePointer: true });
    assert.deepStrictEqual(ctx.fomsGetUploadQueuePolicy().compressConcurrency, 1);
    assert.deepStrictEqual(ctx.fomsGetUploadQueuePolicy().uploadConcurrency, 3);
  }

  {
    const ctx = makeContext();
    const small = { name: 'small.jpg', type: 'image/jpeg', size: 100 * 1024 };
    const result = await ctx.compressImageFile(small);
    assert.strictEqual(result, small);
  }

  {
    const ctx = makeContext();
    const heic = { name: 'photo.heic', type: 'image/heic', size: 5 * 1024 * 1024 };
    const result = await ctx.compressImageFile(heic);
    assert.strictEqual(result, heic);
  }

  {
    const ctx = makeContext();
    const original = { name: 'wide.jpg', type: 'image/jpeg', size: 5 * 1024 * 1024, mockWidth: 4000, mockHeight: 2000 };
    const result = await ctx.compressImageFile(original, { quality: 0.82 });
    assert.notStrictEqual(result, original);
    assert.strictEqual(result.name, 'wide.jpg');
    assert.strictEqual(result.type, 'image/jpeg');
    assert(ctx.getLastCanvas().widthHistory.includes(1920));
    assert(ctx.getLastCanvas().heightHistory.includes(960));
    assert.strictEqual(ctx.getLastCanvas().toBlobQuality, 0.82);
    assert.strictEqual(ctx.getLastCanvas().width, 0, 'canvas cleaned after compression');
  }

  {
    const ctx = makeContext({ blobType: 'image/png' });
    const original = { name: 'wide.jpg', type: 'image/jpeg', size: 5 * 1024 * 1024, mockWidth: 4000, mockHeight: 2000 };
    const result = await ctx.compressImageFile(original);
    assert.strictEqual(result, original);
  }

  {
    const ctx = makeContext();
    let active = 0;
    let maxActive = 0;
    await ctx.fomsRunLimitedQueue([1, 2, 3, 4, 5], 2, async () => {
      active += 1;
      maxActive = Math.max(maxActive, active);
      await new Promise((resolve) => setTimeout(resolve, 5));
      active -= 1;
    });
    assert.strictEqual(maxActive, 2);
  }

  {
    const ctx = makeContext();
    let started = 0;
    let rejected = false;
    try {
      await ctx.fomsRunLimitedQueue([1, 2, 3, 4], 1, async (item) => {
        started += 1;
        if (item === 2) throw new Error('boom');
      });
    } catch (err) {
      rejected = true;
      assert.strictEqual(err.message, 'boom');
    }
    assert.strictEqual(rejected, true);
    assert.strictEqual(started, 2, 'queue must not schedule more workers after rejection');
  }

  {
    let calls = 0;
    const ctx = makeContext({
      onXhrSend: () => {
        calls += 1;
      },
      xhrResponses: [
        { error: true },
        { status: 200, body: { success: true } },
      ],
    });
    const result = await ctx.fomsUploadOrderAttachmentsBatch({
      orderId: 7,
      files: [
        { name: 'fail.txt', type: 'text/plain', size: 1024 },
        { name: 'ok.txt', type: 'text/plain', size: 1024 },
      ],
      useDirectUpload: false,
    });
    assert.strictEqual(result.total, 2);
    assert.strictEqual(result.ok, 1);
    assert.strictEqual(result.results[0].success, false);
    assert.strictEqual(result.results[1].success, true);
    assert.strictEqual(calls, 2, 'fallback failure must not abort remaining files');
  }
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});
