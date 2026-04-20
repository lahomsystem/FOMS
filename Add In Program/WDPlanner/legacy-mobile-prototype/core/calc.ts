import type { Product } from '../types/models';

export type BaseComponentMode = 'select' | 'manual';

export type ManualPricingType = '30cm' | '1m';

export interface AdditionalFee {
  name: string;
  amount: number;
}

export interface BaseComponentInput {
  mode: BaseComponentMode;
  widthMm: number;
  productId?: number | null;
  manualPricing?: {
    pricing_type: ManualPricingType;
    price_30cm?: number;
    price_1cm?: number;
    price_1m?: number;
  };
  additionalFees?: AdditionalFee[];
}

export interface SelectedOptionInput {
  name: string;
  price: number;
  quantity: number;
}

export interface CalcResult {
  basePrice: number;
  additionalPrice: number;
  totalPrice: number;
  detail: string;
}

function ceilToTens(value: number) {
  return Math.ceil(value / 10) * 10;
}

export function computeAutoPrice1cmFrom30cm(price30: number) {
  return ceilToTens((Number(price30) || 0) / 30);
}

export function calcBaseComponentPrice(comp: BaseComponentInput, products: Product[]): { price: number; label: string } {
  const widthMm = Number(comp.widthMm) || 0;
  let price = 0;
  let label = '';

  if (widthMm > 0) {
    if (comp.mode === 'manual') {
      const pricingType = comp.manualPricing?.pricing_type || '30cm';
      if (pricingType === '1m') {
        const price1m = Number(comp.manualPricing?.price_1m) || 0;
        price = (widthMm / 1000) * price1m;
        label = `직접입력(1m) ${widthMm}mm`;
      } else {
        const price30 = Number(comp.manualPricing?.price_30cm) || 0;
        const price1 = Number(comp.manualPricing?.price_1cm) || computeAutoPrice1cmFrom30cm(price30);
        const units30cm = Math.floor(widthMm / 300);
        const remainderMm = widthMm % 300;
        const units1cm = Math.floor(remainderMm / 10);
        price = (units30cm * price30) + (units1cm * price1);
        label = `직접입력(30cm) ${widthMm}mm`;
      }
    } else {
      const productId = Number(comp.productId) || 0;
      const product = products.find(p => p.id === productId);
      if (product) {
        if (product.pricing_type === '1m') {
          price = (widthMm / 1000) * (Number(product.price_1m) || 0);
        } else {
          const units30cm = Math.floor(widthMm / 300);
          const remainderMm = widthMm % 300;
          const units1cm = Math.floor(remainderMm / 10);
          price = (units30cm * (Number(product.price_30cm) || 0)) + (units1cm * (Number(product.price_1cm) || 0));
        }
        label = `${product.name} ${widthMm}mm`;
      }
    }
  }

  const fees = comp.additionalFees || [];
  for (const f of fees) {
    const amt = Number(f.amount) || 0;
    if (amt > 0) price += amt;
  }

  return { price, label };
}

export function calculateAll(params: {
  products: Product[];
  baseComponents: BaseComponentInput[];
  options: SelectedOptionInput[];
}): CalcResult {
  const detailParts: string[] = [];
  let basePrice = 0;

  for (const comp of params.baseComponents) {
    const { price, label } = calcBaseComponentPrice(comp, params.products);
    if (label) detailParts.push(label);

    const fees = comp.additionalFees || [];
    for (const f of fees) {
      const amt = Number(f.amount) || 0;
      if (amt > 0) detailParts.push(`+ ${f.name ? `${f.name} ` : ''}추가금 ${amt}원`);
    }

    basePrice += price;
  }

  let additionalPrice = 0;
  for (const opt of params.options) {
    const p = Number(opt.price) || 0;
    const q = Number(opt.quantity) || 1;
    additionalPrice += p * q;
  }

  return {
    basePrice,
    additionalPrice,
    totalPrice: basePrice + additionalPrice,
    detail: detailParts.join(' / '),
  };
}


