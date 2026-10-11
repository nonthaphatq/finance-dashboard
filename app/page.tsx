'use client'

import React, { useEffect, useState, useMemo } from 'react'
import { useRouter } from 'next/navigation'
import { supabase } from '@/lib/supabaseClient'
import {
  Wallet,
  ArrowUpRight,
  ArrowDownRight,
  Scale,
  RefreshCw,
  LogOut,
  AlertTriangle,
  CheckCircle2,
  Filter,
  Eye,
  EyeOff,
  Search,
  Calendar,
  AlertCircle
} from 'lucide-react'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
} from 'chart.js'
import { Bar, Line } from 'react-chartjs-2'

ChartJS.register(
  CategoryScale,
  LinearScale,
  BarElement,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
)

interface Transaction {
  id: number
  ref_no: string
  txn_at: string
  direction: 'in' | 'out'
  type: string | null
  amount_satang: number
  fee_satang: number
  available_balance_satang: number | null
  account_last4: string | null
  counterparty: string | null
  bank: string
}

export default function DashboardPage() {
  const router = useRouter()
  const [loading, setLoading] = useState(true)
  const [userEmail, setUserEmail] = useState<string | null>(null)

  // Data
  const [transactions, setTransactions] = useState<Transaction[]>([])
  const [parseErrorCount, setParseErrorCount] = useState<number>(0)
  const [lastSyncedAt, setLastSyncedAt] = useState<string | null>(null)

  // Filters
  const [filterDirection, setFilterDirection] = useState<string>('all')
  const [filterType, setFilterType] = useState<string>('all')
  const [searchName, setSearchName] = useState<string>('')
  const [hideNames, setHideNames] = useState<boolean>(false)

  // 1. Check Authentication
  useEffect(() => {
    async function checkAuth() {
      const { data: { session } } = await supabase.auth.getSession()
      if (!session) {
        router.push('/login')
        return
      }
      setUserEmail(session.user.email ?? null)
      fetchData()
    }
    checkAuth()
  }, [router])

  // 2. Fetch Data from Supabase (Read-only via RLS)
  const fetchData = async () => {
    setLoading(true)
    try {
      // Fetch transactions
      const { data: txData, error: txErr } = await supabase
        .from('transactions')
        .select('*')
        .order('txn_at', { ascending: false })

      if (txErr) console.error('Error fetching transactions:', txErr)
      else setTransactions((txData as any) || [])

      // Fetch parse errors count
      const { count: errCount, error: errErr } = await supabase
        .from('parse_errors')
        .select('*', { count: 'exact', head: true })

      if (!errErr) setParseErrorCount(errCount || 0)

      // Fetch sync state
      const { data: syncData, error: syncErr } = await supabase
        .from('sync_state')
        .select('last_synced_at')
        .eq('id', 1)
        .single()

      if (!syncErr && syncData) {
        setLastSyncedAt(syncData.last_synced_at)
      }
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  const handleSignOut = async () => {
    await supabase.auth.signOut()
    router.push('/login')
  }

  // Format THB
  const formatTHB = (amount: number) => {
    return '฿' + (amount).toLocaleString('th-TH', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  }

  // Time calculations
  const { isStale, syncLabel, syncAgo } = useMemo(() => {
    if (!lastSyncedAt) {
      return { isStale: true, syncLabel: 'ไม่เคยซิงก์', syncAgo: 'ไม่มีข้อมูล' }
    }
    const syncDate = new Date(lastSyncedAt)
    const now = new Date()
    const diffMs = now.getTime() - syncDate.getTime()
    const diffMins = Math.floor(diffMs / (1000 * 60))
    const diffHours = Math.floor(diffMins / 60)

    const label = syncDate.toLocaleString('th-TH', {
      timeZone: 'Asia/Bangkok',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })

    let ago = 'เมื่อกี้'
    if (diffMins >= 1 && diffMins < 60) ago = `${diffMins} นาทีที่แล้ว`
    else if (diffHours >= 1 && diffHours < 24) ago = `${diffHours} ชั่วโมงที่แล้ว`
    else if (diffHours >= 24) ago = `${Math.floor(diffHours / 24)} วันที่แล้ว`

    return {
      isStale: diffHours >= 1, // Red warning if > 1 hour
      syncLabel: label,
      syncAgo: ago,
    }
  }, [lastSyncedAt])

  // Current month KPIs
  const currentMonthKPIs = useMemo(() => {
    const now = new Date()
    const currentYearMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`

    let income = 0
    let expense = 0

    // Latest available balance from most recent transaction
    let latestBalance = 0
    if (transactions.length > 0) {
      const sortedByDate = [...transactions].sort((a, b) => new Date(b.txn_at).getTime() - new Date(a.txn_at).getTime())
      for (const t of sortedByDate) {
        if (t.available_balance_satang !== null) {
          latestBalance = t.available_balance_satang / 100
          break
        }
      }
    }

    transactions.forEach(t => {
      const d = new Date(t.txn_at)
      const ym = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
      if (ym === currentYearMonth) {
        const amt = t.amount_satang / 100
        const fee = (t.fee_satang || 0) / 100
        if (t.direction === 'in') {
          income += amt
        } else {
          expense += amt + fee
        }
      }
    })

    return {
      latestBalance,
      incomeMonth: income,
      expenseMonth: expense,
      netMonth: income - expense,
    }
  }, [transactions])

  // Filtered transactions
  const filteredTransactions = useMemo(() => {
    return transactions.filter(t => {
      if (filterDirection !== 'all' && t.direction !== filterDirection) return false
      if (filterType !== 'all' && t.type !== filterType) return false
      if (searchName) {
        const name = (t.counterparty || '').toLowerCase()
        if (!name.includes(searchName.toLowerCase())) return false
      }
      return true
    })
  }, [transactions, filterDirection, filterType, searchName])

  // Unique types for filter dropdown
  const uniqueTypes = useMemo(() => {
    const s = new Set<string>()
    transactions.forEach(t => {
      if (t.type) s.add(t.type)
    })
    return Array.from(s)
  }, [transactions])

  // Chart 1: Monthly Cash Flow Data
  const monthlyChartData = useMemo(() => {
    const monthsMap: Record<string, { in: number; out: number }> = {}

    transactions.forEach(t => {
      const d = new Date(t.txn_at)
      const ym = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
      if (!monthsMap[ym]) monthsMap[ym] = { in: 0, out: 0 }
      const amt = t.amount_satang / 100
      const fee = (t.fee_satang || 0) / 100
      if (t.direction === 'in') monthsMap[ym].in += amt
      else monthsMap[ym].out += amt + fee
    })

    const labels = Object.keys(monthsMap).sort()
    const inData = labels.map(m => monthsMap[m].in)
    const outData = labels.map(m => monthsMap[m].out)

    return {
      labels,
      datasets: [
        {
          label: 'เงินเข้า (บาท)',
          data: inData,
          backgroundColor: '#22c55e',
        },
        {
          label: 'เงินออก (รวมค่าธรรมเนียม)',
          data: outData,
          backgroundColor: '#ef4444',
        },
      ],
    }
  }, [transactions])

  // Chart 2: Balance over time
  const balanceChartData = useMemo(() => {
    const valid = transactions
      .filter(t => t.available_balance_satang !== null)
      .sort((a, b) => new Date(a.txn_at).getTime() - new Date(b.txn_at).getTime())

    const labels = valid.map(t => {
      const d = new Date(t.txn_at)
      return `${d.getDate()}/${d.getMonth() + 1} ${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`
    })
    const data = valid.map(t => (t.available_balance_satang || 0) / 100)

    return {
      labels,
      datasets: [
        {
          label: 'ยอดถอนได้ (บาท)',
          data: data,
          borderColor: '#3b82f6',
          backgroundColor: 'rgba(59, 130, 246, 0.1)',
          fill: true,
          tension: 0.3,
          pointRadius: 4,
        },
      ],
    }
  }, [transactions])

  if (loading && transactions.length === 0) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50">
        <div className="flex flex-col items-center gap-3">
          <RefreshCw className="w-8 h-8 text-blue-600 animate-spin" />
          <p className="text-slate-500 text-sm">กำลังโหลดข้อมูลการเงิน...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-slate-50 pb-16">
      {/* Top Navbar */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-30 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-2xl">💰</span>
            <h1 className="text-xl font-bold text-slate-800">Finance Dashboard</h1>
          </div>
          <div className="flex items-center gap-4">
            <button
              onClick={fetchData}
              className="p-2 text-slate-500 hover:text-slate-800 hover:bg-slate-100 rounded-lg transition"
              title="รีเฟรชข้อมูล"
            >
              <RefreshCw className={`w-5 h-5 ${loading ? 'animate-spin' : ''}`} />
            </button>
            <div className="text-xs text-slate-500 hidden sm:block border-l border-slate-200 pl-4">
              {userEmail}
            </div>
            <button
              onClick={handleSignOut}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50 rounded-lg transition"
            >
              <LogOut className="w-4 h-4" />
              <span>ออกจากระบบ</span>
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-6 space-y-6">
        {/* Health Status Banner */}
        {isStale ? (
          <div className="p-4 bg-red-50 border border-red-200 text-red-800 rounded-2xl flex items-start sm:items-center justify-between gap-4">
            <div className="flex items-start gap-3">
              <AlertTriangle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5 sm:mt-0" />
              <div className="text-sm">
                <span className="font-semibold">⚠️ ข้อมูลอาจล้าสมัย</span> — ซิงก์ล่าสุด: <strong>{syncLabel}</strong> ({syncAgo})
              </div>
            </div>
            <div className="text-xs bg-red-100 text-red-700 px-3 py-1 rounded-full whitespace-nowrap">
              Parse Errors: {parseErrorCount}
            </div>
          </div>
        ) : (
          <div className="p-4 bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-2xl flex items-start sm:items-center justify-between gap-4">
            <div className="flex items-start gap-3">
              <CheckCircle2 className="w-5 h-5 text-emerald-600 flex-shrink-0 mt-0.5 sm:mt-0" />
              <div className="text-sm">
                <span className="font-semibold">✅ ข้อมูลเป็นปัจจุบัน</span> — ซิงก์ล่าสุด: <strong>{syncLabel}</strong> ({syncAgo})
              </div>
            </div>
            <div className="text-xs bg-emerald-100 text-emerald-700 px-3 py-1 rounded-full whitespace-nowrap">
              Parse Errors: {parseErrorCount}
            </div>
          </div>
        )}

        {/* Disclaimer Note */}
        <div className="p-3 bg-blue-50 border border-blue-100 text-blue-700 rounded-xl text-xs flex items-center gap-2">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          <span>⚠️ ตัวเลขนี้แสดงเฉพาะรายการที่ระบบอ่านจากอีเมลได้เท่านั้น อาจต่ำกว่าความเป็นจริงถ้ามีอีเมลประเภทที่ยังไม่รองรับ</span>
        </div>

        {/* 4 Summary Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Card 1: Balance */}
          <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm">
            <div className="flex items-center justify-between text-slate-500 mb-2">
              <span className="text-xs font-semibold uppercase tracking-wider">ยอดถอนได้ล่าสุด (บัญชีนี้)</span>
              <Wallet className="w-5 h-5 text-blue-600" />
            </div>
            <div className="text-2xl font-bold text-slate-800">
              {formatTHB(currentMonthKPIs.latestBalance)}
            </div>
            <p className="text-xs text-slate-400 mt-1">อัปเดตจากรายการล่าสุด</p>
          </div>

          {/* Card 2: Income */}
          <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm">
            <div className="flex items-center justify-between text-slate-500 mb-2">
              <span className="text-xs font-semibold uppercase tracking-wider text-emerald-600">💚 เงินเข้าเดือนนี้</span>
              <ArrowDownRight className="w-5 h-5 text-emerald-600" />
            </div>
            <div className="text-2xl font-bold text-slate-800">
              {formatTHB(currentMonthKPIs.incomeMonth)}
            </div>
            <p className="text-xs text-emerald-600 mt-1">
              +{formatTHB(currentMonthKPIs.incomeMonth)}
            </p>
          </div>

          {/* Card 3: Expense */}
          <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm">
            <div className="flex items-center justify-between text-slate-500 mb-2">
              <span className="text-xs font-semibold uppercase tracking-wider text-red-600">🔴 เงินออกเดือนนี้</span>
              <ArrowUpRight className="w-5 h-5 text-red-600" />
            </div>
            <div className="text-2xl font-bold text-slate-800">
              {formatTHB(currentMonthKPIs.expenseMonth)}
            </div>
            <p className="text-xs text-red-600 mt-1">
              -{formatTHB(currentMonthKPIs.expenseMonth)} (รวมค่าธรรมเนียม)
            </p>
          </div>

          {/* Card 4: Net */}
          <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm">
            <div className="flex items-center justify-between text-slate-500 mb-2">
              <span className="text-xs font-semibold uppercase tracking-wider text-blue-600">💙 สุทธิเดือนนี้</span>
              <Scale className="w-5 h-5 text-blue-600" />
            </div>
            <div className={`text-2xl font-bold ${currentMonthKPIs.netMonth >= 0 ? 'text-emerald-600' : 'text-red-600'}`}>
              {formatTHB(currentMonthKPIs.netMonth)}
            </div>
            <p className="text-xs text-slate-400 mt-1">เงินเข้า ลบ เงินออก</p>
          </div>
        </div>

        {/* Charts Section */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm">
            <h3 className="text-base font-bold text-slate-800 mb-4">📈 กระแสเงินสดรายเดือน</h3>
            <div className="h-64 flex items-center justify-center">
              {monthlyChartData.labels.length > 0 ? (
                <Bar
                  data={monthlyChartData}
                  options={{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { position: 'top' as const } },
                  }}
                />
              ) : (
                <p className="text-sm text-slate-400">ยังไม่มีข้อมูลเพียงพอ</p>
              )}
            </div>
          </div>

          <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm">
            <h3 className="text-base font-bold text-slate-800 mb-4">📉 ยอดถอนได้ตามเวลา</h3>
            <div className="h-64 flex items-center justify-center">
              {balanceChartData.labels.length > 0 ? (
                <Line
                  data={balanceChartData}
                  options={{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { position: 'top' as const } },
                  }}
                />
              ) : (
                <p className="text-sm text-slate-400">ยังไม่มีข้อมูลยอดคงเหลือ</p>
              )}
            </div>
          </div>
        </div>

        {/* Transactions Table & Filters */}
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
          {/* Header & Filter Controls */}
          <div className="p-6 border-b border-slate-200 space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <h3 className="text-lg font-bold text-slate-800">
                📋 รายการทั้งหมด ({filteredTransactions.length})
              </h3>
              {/* Hide Name Toggle */}
              <button
                onClick={() => setHideNames(!hideNames)}
                className="flex items-center gap-2 px-3 py-1.5 text-xs font-medium rounded-lg border border-slate-200 hover:bg-slate-50 transition w-fit"
              >
                {hideNames ? <EyeOff className="w-4 h-4 text-slate-500" /> : <Eye className="w-4 h-4 text-slate-500" />}
                <span>{hideNames ? 'กำลังซ่อนชื่อผู้รับ' : 'ซ่อนชื่อผู้รับเงิน'}</span>
              </button>
            </div>

            {/* Filter Bar */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {/* Search */}
              <div className="relative">
                <Search className="w-4 h-4 absolute left-3 top-3 text-slate-400" />
                <input
                  type="text"
                  placeholder="ค้นหาชื่อผู้รับ/โอน..."
                  value={searchName}
                  onChange={(e) => setSearchName(e.target.value)}
                  className="w-full pl-9 pr-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs focus:outline-none focus:ring-2 focus:ring-blue-500 focus:bg-white transition"
                />
              </div>

              {/* Direction Dropdown */}
              <select
                value={filterDirection}
                onChange={(e) => setFilterDirection(e.target.value)}
                className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs focus:outline-none focus:ring-2 focus:ring-blue-500 focus:bg-white transition"
              >
                <option value="all">ทิศทาง: ทั้งหมด</option>
                <option value="in">เงินเข้า 💚</option>
                <option value="out">เงินออก 🔴</option>
              </select>

              {/* Type Dropdown */}
              <select
                value={filterType}
                onChange={(e) => setFilterType(e.target.value)}
                className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs focus:outline-none focus:ring-2 focus:ring-blue-500 focus:bg-white transition"
              >
                <option value="all">ประเภท: ทั้งหมด</option>
                {uniqueTypes.map(t => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </div>
          </div>

          {/* Table */}
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-600">
              <thead className="bg-slate-50 text-slate-500 uppercase font-semibold text-[11px] border-b border-slate-200">
                <tr>
                  <th className="py-3 px-4">วันที่-เวลา</th>
                  <th className="py-3 px-4">ทิศทาง</th>
                  <th className="py-3 px-4">ประเภท</th>
                  <th className="py-3 px-4 text-right">จำนวนเงิน (฿)</th>
                  <th className="py-3 px-4 text-right">ค่าธรรมเนียม (฿)</th>
                  <th className="py-3 px-4 text-right">รวมจ่าย (฿)</th>
                  <th className="py-3 px-4 text-right">ยอดถอนได้ (฿)</th>
                  <th className="py-3 px-4">บัญชี</th>
                  <th className="py-3 px-4">ผู้รับ/โอน</th>
                  <th className="py-3 px-4">เลขที่รายการ</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredTransactions.length === 0 ? (
                  <tr>
                    <td colSpan={10} className="py-8 text-center text-slate-400">
                      ไม่พบรายการที่ตรงกับเงื่อนไข
                    </td>
                  </tr>
                ) : (
                  filteredTransactions.map((t) => {
                    const d = new Date(t.txn_at)
                    const dateFormatted = d.toLocaleString('th-TH', {
                      timeZone: 'Asia/Bangkok',
                      year: 'numeric',
                      month: '2-digit',
                      day: '2-digit',
                      hour: '2-digit',
                      minute: '2-digit',
                    })
                    const amt = t.amount_satang / 100
                    const fee = (t.fee_satang || 0) / 100
                    const totalOut = amt + fee
                    const bal = t.available_balance_satang !== null ? t.available_balance_satang / 100 : null

                    const counterpartyDisplay = hideNames
                      ? '***'
                      : (t.counterparty || '-')

                    return (
                      <tr key={t.id} className="hover:bg-slate-50/80 transition">
                        <td className="py-3 px-4 whitespace-nowrap font-medium text-slate-800">{dateFormatted}</td>
                        <td className="py-3 px-4 whitespace-nowrap">
                          {t.direction === 'in' ? (
                            <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-100 text-emerald-700">เข้า 💚</span>
                          ) : (
                            <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-red-100 text-red-700">ออก 🔴</span>
                          )}
                        </td>
                        <td className="py-3 px-4 whitespace-nowrap text-slate-500">{t.type || '-'}</td>
                        <td className="py-3 px-4 text-right whitespace-nowrap font-semibold text-slate-800">
                          {amt.toLocaleString('th-TH', { minimumFractionDigits: 2 })}
                        </td>
                        <td className="py-3 px-4 text-right whitespace-nowrap text-slate-500">
                          {fee > 0 ? fee.toLocaleString('th-TH', { minimumFractionDigits: 2 }) : '-'}
                        </td>
                        <td className="py-3 px-4 text-right whitespace-nowrap font-semibold text-red-600">
                          {t.direction === 'out' ? totalOut.toLocaleString('th-TH', { minimumFractionDigits: 2 }) : '-'}
                        </td>
                        <td className="py-3 px-4 text-right whitespace-nowrap font-semibold text-slate-700">
                          {bal !== null ? bal.toLocaleString('th-TH', { minimumFractionDigits: 2 }) : '-'}
                        </td>
                        <td className="py-3 px-4 whitespace-nowrap font-mono text-[11px] text-slate-500">
                          {t.account_last4 ? `...${t.account_last4}` : '-'}
                        </td>
                        <td className="py-3 px-4 whitespace-nowrap max-w-xs truncate text-slate-700">
                          {counterpartyDisplay}
                        </td>
                        <td className="py-3 px-4 whitespace-nowrap font-mono text-[11px] text-slate-400">
                          {t.ref_no}
                        </td>
                      </tr>
                    )
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      </main>
    </div>
  )
}

