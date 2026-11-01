/**
 * 서버 계산 = 화면 계산 계약(플랜 C10-6) — pricing-core.js 를 VM 에 올려 받은 입력 묶음을 화면 계산으로 돌린다.
 * 입력(표준 입력 JSON): {"cases": [{"kind": "estimate", "components", "products", "options"} |
 *                                   {"kind": "aggregate", "estimates", "coupon", "shipping", "included"}]}
 * 출력(표준 출력 JSON): 같은 차례의 결과 목록. 계산 실패(가로 글 못 읽음)는 {"ok": false}.
 * pytest 가 node 로 부른다(tests/contracts/wdcalculator/test_server_pricing_contract.py).
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const repoRoot = path.join(__dirname, "..", "..");
const code = fs.readFileSync(path.join(repoRoot, "static", "js", "wdcalculator", "pricing-core.js"), "utf8");
const sandbox = { window: null, globalThis: null, document: {}, console };
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(code, sandbox);

const estimateMath = sandbox.wdcComputeCurrentEstimateMath;
const aggregate = sandbox.wdcComputeAggregateTotals;
if (typeof estimateMath !== "function" || typeof aggregate !== "function") {
    throw new Error("pricing-core.js 계산 함수가 없다");
}

function runEstimate(item) {
    let math;
    try {
        math = estimateMath(item.components, item.products, item.options, function (n) {
            return String(Math.round(Number(n) || 0));
        });
    } catch (error) {
        return { ok: false };
    }
    return {
        ok: true,
        base_calculate: math.basePriceCalculate,
        base_collect: math.basePriceCollect,
        additional: math.additionalPrice,
        total_calculate: math.totalPriceCalculate,
        total_collect: math.totalPriceCollect,
        components: math.normalizedComponents.length,
        won_total: Number.isFinite(math.totalPriceCollect) ? Math.round(math.totalPriceCollect) : null,
    };
}

const input = JSON.parse(fs.readFileSync(0, "utf8"));
const out = input.cases.map(function (item) {
    if (item.kind === "aggregate") {
        return aggregate(item.estimates, item.coupon, item.shipping, item.included);
    }
    return runEstimate(item);
});
process.stdout.write(JSON.stringify(out));
