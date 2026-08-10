import { apiClient } from './client'
import type {
  AddCatalogCardRequest,
  AddCustomCardRequest,
  CatalogListResponse,
  WalletCard,
  WalletListResponse,
} from './types'

export function fetchCatalog(): Promise<CatalogListResponse> {
  return apiClient<CatalogListResponse>('/api/cards/')
}

export function fetchWallet(): Promise<WalletListResponse> {
  return apiClient<WalletListResponse>('/api/wallet/')
}

export function addCatalogCard(
  payload: AddCatalogCardRequest,
): Promise<WalletCard> {
  return apiClient<WalletCard>('/api/wallet/', {
    method: 'POST',
    body: payload,
  })
}

export function addCustomCard(
  payload: AddCustomCardRequest,
): Promise<WalletCard> {
  return apiClient<WalletCard>('/api/wallet/', {
    method: 'POST',
    body: payload,
  })
}

/** Hard-deletes wallet row and cascades transactions, the path id wallet `id`- not card_product_id. */
export function deleteWalletCard(walletId: number): Promise<void> {
  return apiClient<void>(`/api/wallet/${walletId}/`, { method: 'DELETE' })
}
