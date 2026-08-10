import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

import { GuestRoute, ProtectedRoute } from './components/ProtectedRoute'
import { AppLayout } from './layouts/AppLayout'
import { LoginPage, RegisterPage } from './pages/AuthPages'
import { PlaceholderPage } from './pages/PlaceholderPage'
import { ReviewPage } from './pages/ReviewPage'
import { UploadPage } from './pages/UploadPage'
import { WalletPage } from './pages/WalletPage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<GuestRoute />}>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
        </Route>

        <Route element={<ProtectedRoute />}>
          <Route element={<AppLayout />}>
            <Route
              path="/"
              element={
                <PlaceholderPage
                  title="Dashboard"
                  note="Summary from /api/summary/ lands in the next modules. Use Wallet to add cards first."
                />
              }
            />
            <Route path="/wallet" element={<WalletPage />} />
            <Route path="/upload" element={<UploadPage />} />
            <Route path="/review" element={<ReviewPage />} />
            <Route
              path="/recommendations"
              element={
                <PlaceholderPage
                  title="Recommendations"
                  note="Ranked cards from /api/recommendations/ come next."
                />
              }
            />
            <Route
              path="/transactions"
              element={
                <PlaceholderPage
                  title="Transactions"
                  note="Transaction table from /api/transactions/ comes next."
                />
              }
            />
          </Route>
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
