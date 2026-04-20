export type PricingType = '30cm' | '1m';

export interface Product {
  id: number;
  name: string;
  pricing_type: PricingType;
  price_30cm?: number;
  price_1cm?: number;
  price_1m?: number;
}

export interface AdditionalOptionCategory {
  id: number;
  name: string;
}

export interface AdditionalOption {
  id: number;
  category_id: number;
  name: string;
  price: number;
}

export interface NotesCategory {
  id: number;
  name: string;
}

export interface NotesOption {
  id: number;
  category_id: number;
  name: string;
}

export interface EstimateRow {
  id: number;
  customer_name: string;
  estimate_data_json: string; // JSON.stringify(estimate_data)
  created_at: string; // ISO
  updated_at: string; // ISO
}

export interface EstimateHistoryRow {
  id: number;
  estimate_id: number;
  estimate_data_json: string;
  created_at: string;
}


