/** Shapes returned by the Django/DRF backend.*/

export type User = {
  id: number
  username: string
  email: string
}

export type TokenPair = {
  access: string
  refresh: string
}

export type AccessTokenResponse = {
  access: string
}

export type RegisterRequest = {
  username: string
  email: string
  password: string
  password2: string
}

export type LoginRequest = {
  username: string
  password: string
}

/** DRF validation errors are field -> string[] or nested. `detail` is used for auth failures. */
export type ApiErrorBody = {
  detail?: string | string[]
  [field: string]: unknown
}

/** Money fields from Django are decimal strings, e.g. "25.00". */
export type MoneyString = string

export type CatalogCard = {
  id: number
  name: string
  issuer: string
  network: string
  card_type: string
  annual_fee: MoneyString
  base_reward_rate: MoneyString
  signup_bonus: MoneyString
  signup_bonus_required_spending: MoneyString
}

export type CatalogListResponse = {
  count: number
  cards: CatalogCard[]
}

/** Wallet row. `id` is user_card_id for uploads / DELETE /api/wallet/<id>/. */
export type WalletCard = {
  id: number
  card_product_id: number
  card_name: string
  issuer: string
  network: string
  is_catalog: boolean
  is_active: boolean
}

export type WalletListResponse = {
  count: number
  cards: WalletCard[]
}

export type AddCatalogCardRequest = {
  card_product_id: number
}

export type AddCustomCardRequest = {
  name: string
  issuer: string
  network: string
}

export type UploadSummary = {
  rows: number
  merchants: number
  created: number
  updated: number
  needs_review: number
  coverage_pct: number
}

/** One file outcome after POST /api/upload/ (normalized for UI). */
export type UploadFileResult = {
  ok: boolean
  filename: string
  detail?: string
  upload_id?: number
  status?: string
  user_card_id?: number
  summary?: UploadSummary
  http_status?: number
  current_user_card_ids?: number[]
  requested_user_card_id?: number
}

export type UploadBatchResponse = {
  count: number
  succeeded: number
  failed: number
  results: UploadFileResult[]
}

export type UploadListItem = {
  upload_id: number
  filename: string
  status: string
  transaction_count: number
  user_card_id: number | null
  card_name: string | null
  issuer: string | null
  created_at: string
  updated_at: string
}

export type UploadListResponse = {
  count: number
  uploads: UploadListItem[]
}

export type ReassignUploadResponse = {
  upload_id: number
  user_card_id: number
  card_name: string
  issuer: string
  transactions_updated: number
}

export type ReviewMerchant = {
  merchant_key: string
  display_name: string
  sample_description: string
  transaction_count: number
  total_amount: MoneyString
}

export type ReviewQueueResponse = {
  count: number
  truncated: boolean
  categories: string[]
  merchants: ReviewMerchant[]
}

export type ReviewAnswerRequest = {
  merchant_key: string
  category: string
}

export type ReviewAnswerResponse = {
  merchant_key: string
  category: string
  transactions_updated: number
}

export type SummaryMonthBreakdown = {
  month: string
  transaction_count: number
}

export type SummaryPeriod = {
  earliest: string | null
  latest: string | null
  days_span: number
  months_covered: number
  months_breakdown: SummaryMonthBreakdown[]
}

/** GET /api/summary/ — money fields are strings AND categorized_pct is also a string */
export type SpendSummaryResponse = {
  period: SummaryPeriod
  by_category: Record<string, MoneyString>
  annualized: Record<string, MoneyString>
  total_spend: MoneyString
  transaction_count: number
  unresolved_count: number
  unresolved_amount: MoneyString
  categorized_pct: string
}

export type SignupBonusStatus =
  | 'met'
  | 'not_met'
  | 'insufficient_data'
  | 'no_bonus'

export type RecommendationExplanationLine = {
  category: string
  rate: MoneyString
  effective_rate: MoneyString
  annualized_spend: MoneyString
  value: MoneyString
}

export type RecommendationCard = {
  rank: number
  card_id: number
  card_name: string
  issuer: string
  reward_currency: string
  headline: string
  spending_score: MoneyString
  annual_fee: MoneyString
  signup_bonus_score: MoneyString
  signup_bonus_status: SignupBonusStatus | string
  signup_bonus_note: string
  signup_bonus_detail: Record<string, unknown>
  total_score: MoneyString
  ongoing_annual_value: MoneyString
  break_even_annual_spend: MoneyString | null
  explanation: RecommendationExplanationLine[]
  /** Present only when this card ties with another. */
  rank_note?: string
}

export type RecommendationsResponse = {
  confidence: string
  confidence_note: string
  value_basis: {
    currency: string
    period: string
    months_of_data: number
    point_value_cents: string
    note: string
  }
  recommendations: RecommendationCard[]
}

export type LedgerEntryType = 'spend' | 'refund' | 'payment' | 'adjustment' | string

export type TransactionRow = {
  id: number
  upload_id: number
  filename: string
  user_card_id: number
  card_name: string
  issuer: string
  transaction_date: string
  amount: MoneyString
  description: string
  normalized_description: string
  merchant_key: string
  category: string
  entry_type: LedgerEntryType
  resolution_source: string
  confidence: number
}

export type TransactionsResponse = {
  count: number
  truncated: boolean
  transactions: TransactionRow[]
}
