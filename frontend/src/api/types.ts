/** Shapes returned by the Django/DRF backend. Keep monetary values as strings elsewhere. */

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
