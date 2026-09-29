"use strict";

const fs = require("fs");
const searchJsPath = process.argv[2];
const listeners = {};
const storage = {};
let assigned = null;
let assignCalls = 0;
let prevented = false;
let resultLinks = [];

const input = {
  id: "foms-search-input",
  value: "유청",
  focus: () => {},
  getAttribute: (name) => name === "data-search-history-url" ? "/erp/history/" : null,
};
const group = { value: "all" };
const resultsRoot = { querySelectorAll: () => resultLinks, innerHTML: "" };
const resultsWrap = { hidden: true };
const recentList = { innerHTML: "", appendChild: () => {} };
const dialog = {
  querySelectorAll: () => [],
  showModal: () => {},
  close: () => {},
  contains: () => true,
};

global.localStorage = {
  getItem: (key) => storage[key] || null,
  setItem: (key, value) => { storage[key] = value; },
};
global.window = {
  location: {
    origin: "https://example.test",
    assign: (url) => {
      assigned = url;
      assignCalls += 1;
    },
  },
  setTimeout,
};
global.document = {
  getElementById: (id) => ({
    "foms-search-overlay": dialog,
    "foms-search-input": input,
    "foms-search-group": group,
    "foms-search-results": resultsRoot,
    "foms-search-results-wrap": resultsWrap,
    "foms-search-recent-list": recentList,
  }[id] || null),
  addEventListener: (name, handler) => { listeners[name] = handler; },
  body: { addEventListener: () => {} },
  createElement: () => ({ setAttribute: () => {}, appendChild: () => {} }),
};

eval(fs.readFileSync(searchJsPath, "utf8"));

function event(type, overrides = {}) {
  return {
    target: input,
    key: type === "keydown" ? "Enter" : undefined,
    isComposing: false,
    keyCode: 13,
    preventDefault: () => { prevented = true; },
    ...overrides,
  };
}

function resetSearch(groupValue) {
  listeners.click({
    target: { closest: (selector) => selector === "[data-foms-search-open]" ? {} : null },
    preventDefault: () => {},
  });
  input.value = "유청";
  group.value = groupValue;
  assigned = null;
  assignCalls = 0;
  prevented = false;
  resultLinks = [];
}

resetSearch("all");
listeners.keydown(event("keydown"));
if (!prevented || assigned !== "/erp/history/?q=%EC%9C%A0%EC%B2%AD&from_search=1") {
  throw new Error(`normal Enter failed: ${assigned}`);
}
listeners.search(event("search"));
if (assignCalls !== 1) throw new Error(`duplicate navigation: ${assignCalls}`);

const HISTORY_HREF = "/erp/history/?q=%EC%9C%A0%EC%B2%AD&from_search=1";

// 어느 범주 탭에 있든 검색 키는 전체 기준 결과 화면으로 간다(2026-09-29).
for (const groupValue of ["customer", "order", "drawing"]) {
  resetSearch(groupValue);
  listeners.keydown(event("keydown"));
  listeners.search(event("search"));
  if (!prevented || assigned !== HISTORY_HREF || assignCalls !== 1) {
    throw new Error(`${groupValue} tab must search all: ${assigned} x${assignCalls}`);
  }
}

// 다시 열면 지난번 범주 탭이 남지 않고 전체로 돌아간다.
group.value = "drawing";
listeners.click({
  target: { closest: (selector) => selector === "[data-foms-search-open]" ? {} : null },
  preventDefault: () => {},
});
if (group.value !== "all") throw new Error(`reopen kept group: ${group.value}`);

function clickOn(matchSelector, node) {
  listeners.click({
    target: { closest: (selector) => selector === matchSelector ? node : null },
    preventDefault: () => { prevented = true; },
  });
}

// 최근 검색 칩 = 검색 키와 같은 전체 결과 화면.
resetSearch("order");
input.value = "";
clickOn("[data-foms-search-recent-term]", {
  getAttribute: (name) => name === "data-foms-search-recent-term" ? "유청" : null,
});
if (!prevented || assigned !== HISTORY_HREF || assignCalls !== 1) {
  throw new Error(`recent chip must match Enter: ${assigned} x${assignCalls}`);
}

// 미리보기 아래 "전체 결과 보기"도 같은 곳.
resetSearch("customer");
clickOn("[data-search-history-fallback]", {});
if (!prevented || assigned !== HISTORY_HREF || assignCalls !== 1) {
  throw new Error(`history link must match Enter: ${assigned} x${assignCalls}`);
}

resetSearch("all");
listeners.keydown(event("keydown", { isComposing: true, keyCode: 229 }));
if (prevented || assigned !== null) throw new Error("composing Enter redirected early");

listeners.search(event("search"));
if (!prevented || assigned !== "/erp/history/?q=%EC%9C%A0%EC%B2%AD&from_search=1") {
  throw new Error(`IME search event failed: ${assigned}`);
}

resetSearch("all");
resultLinks = [{
  classList: { toggle: () => {} },
  scrollIntoView: () => {},
  getAttribute: (name) => name === "href" ? "/erp/order/123" : null,
}];
listeners.keydown(event("keydown", { key: "ArrowDown" }));
listeners.keydown(event("keydown"));
if (assigned !== "/erp/order/123" || assignCalls !== 1) {
  throw new Error(`highlighted result did not win: ${assigned}`);
}

console.log("FOMS_SEARCH_ENTER_OK");
