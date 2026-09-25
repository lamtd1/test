const BASE = "http://localhost:8000/api/v1";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new ApiError(res.status, `${res.status} ${path}: ${body}`);
  }
  return res.json();
}

export interface SoftPreference {
  key: string;
  params: Record<string, unknown>;
  weight: number;
  confidence: "high" | "low";
  source: "user_stated" | "agent_inferred";
  raw_quote: string | null;
}

export interface CriteriaSchema {
  hard_constraints: {
    bedrooms_min: number | null;
    bathrooms_min: number | null;
    area_min_m2: number | null;
    floor_min: number | null;
    district: string[] | null;
    price_max_vnd: number | null;
  };
  soft_preferences: SoftPreference[];
  deal_breakers: unknown[];
  context: Record<string, unknown>;
  completeness: number;
}

export interface LeverageScenario {
  label: string;
  ltv: number;
  price_max_vnd: number;
  installment_promo_vnd: number;
  installment_float_vnd: number;
}

export interface Envelope {
  price_min_vnd: number;
  price_max_vnd: number;
  price_target_vnd: number;
  installment_promo_vnd: number;
  installment_float_vnd: number;
  binding_constraint: "capacity" | "equity";
  income_bucket: string;
  scenarios: LeverageScenario[];
  disclaimer: string;
}

export interface UnitFacts {
  unit_id: string;
  project_name: string;
  district: string;
  bedrooms: number;
  bathrooms: number;
  area_sqm: number;
  floor: number;
  total_floors: number;
  balcony_dir: string | null;
  view_type: string | null;
  price_vnd: number;
  handover_date: string | null;
}

export interface RankedUnit {
  unit: UnitFacts;
  match_score: number;
  reasons: string[];
  tradeoffs: string[];
}

export interface RankedUnitInternal extends RankedUnit {
  business_priority: number;
  days_on_market: number;
  is_removed: boolean;
}

export interface ShortlistResponse {
  state: string;
  price_min_vnd?: number | null;
  price_max_vnd?: number | null;
  units?: RankedUnit[];
}

export const api = {
  createSession: () => request<{ session_id: string }>("/sessions", { method: "POST" }),

  sendMessage: (sessionId: string, text: string) =>
    request<{ reply: string; criteria: CriteriaSchema; completeness: number }>(
      `/sessions/${sessionId}/messages`,
      { method: "POST", body: JSON.stringify({ text }) },
    ),

  computeFinance: (
    sessionId: string,
    input: {
      cash_available_vnd: number;
      income_monthly_vnd: number;
      existing_debt_monthly_vnd: number;
      loan_term_years: number;
    },
  ) =>
    request<Envelope>(`/sessions/${sessionId}/finance`, {
      method: "POST",
      body: JSON.stringify(input),
    }),

  getShortlist: (sessionId: string) =>
    request<ShortlistResponse>(`/sessions/${sessionId}/shortlist`),

  getQueue: () =>
    request<{
      queue: { session_id: string; created_at: string; price_min_vnd: number; price_max_vnd: number }[];
    }>("/queue"),

  getReview: (sessionId: string) =>
    request<{
      session_id: string;
      state: string;
      criteria: CriteriaSchema | null;
      envelope: Envelope | null;
      units: RankedUnitInternal[];
    }>(`/sessions/${sessionId}/review`),

  removeUnit: (sessionId: string, unitId: string, reason: string) =>
    request(`/sessions/${sessionId}/units/${unitId}/remove`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),

  approve: (sessionId: string) =>
    request(`/sessions/${sessionId}/approve`, { method: "POST" }),
};

export function formatVnd(v: number | null | undefined): string {
  if (v == null) return "—";
  return `${(v / 1_000_000_000).toFixed(2)} tỷ`;
}

/** Dùng cho tiền trả góp/tháng — hiển thị bằng triệu thay vì tỷ để không làm tròn về 0.0x. */
export function formatVndMonthly(v: number | null | undefined): string {
  if (v == null) return "—";
  return `${(v / 1_000_000).toFixed(1)} triệu`;
}
