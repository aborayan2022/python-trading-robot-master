/**
 * PyRobot Management Console — Frontend Application Logic
 * Vanilla JavaScript (ES6+) — Zero External Dependencies
 */

(function () {
  'use strict';

  // ── I18N Translations Dictionary ──────────────────────────────────────────
  const I18N = {
    ar: {
      nav_console_sub: "غرفة قيادة المدير",
      tab_overview: "نظرة عامة",
      tab_control: "غرفة التحكم",
      tab_audit: "سجل التدقيق",
      tab_markets: "الأسواق",
      btn_login: "دخول / تبديل",
      metric_engine_status: "حالة المحرك",
      metric_equity: "رأس المال (Equity)",
      sub_today: "اليوم",
      metric_drawdown: "التراجع (Drawdown)",
      metric_risk_gates: "بوابات الأمان",
      gate_kill_switch: "مفتاح الإيقاف:",
      gate_circuit_breaker: "قاطع الدائرة:",
      gate_model_scale: "مخاطر النموذج:",
      chart_equity_title: "منحنى رأس المال المباشر",
      freshness_label: "عمر البيانات:",
      panel_signals_title: "تدفق الإشارات المباشرة",
      no_signals_yet: "لا توجد إشارات بعد...",
      panel_positions_title: "المراكز المفتوحة (Positions)",
      th_symbol: "الرمز",
      th_qty: "الكمية",
      th_entry_price: "سعر الدخول",
      th_cur_price: "السعر الحالي",
      th_market_val: "القيمة السوقية",
      th_unrealized_pnl: "ربح/خسارة غير محققة",
      no_open_positions: "لا توجد مراكز مفتوحة حالياً",
      panel_orders_title: "الأوامر الحديثة (Orders)",
      th_order_id: "رقم الأمر",
      th_side: "الاتجاه",
      th_status: "الحالة",
      th_time: "الوقت",
      no_orders_yet: "لا توجد أوامر بعد",
      control_restricted_title: "صلاحية المدير مطلوبة للتحكم",
      control_restricted_desc: "أنت تتصفح حالياً بصفة مراقب. يلزم تسجيل الدخول بدور MANAGER لإجراء أي تعديلات أو تشغيل/إيقاف.",
      ctrl_lifecycle_title: "دورة حياة المحرك",
      btn_start: "تشغيل (Start)",
      btn_pause: "إيقاف مؤقت (Pause)",
      btn_resume: "استئناف (Resume)",
      btn_stop: "إيقاف رشيق (Stop)",
      ctrl_emergency_title: "مفتاح الطوارئ (Emergency Kill Switch)",
      ctrl_kill_desc: "تفعيل مفتاح الطوارئ يوقف كافة عمليات التداول فورا ويرفض أي أوامر جديدة حتى إعادة الضبط اليدوي المعتمد.",
      btn_kill_activate: "تفعيل مفتاح الإيقاف الطارئ",
      btn_kill_reset: "إعادة ضبط المفتاح (Reset)",
      ctrl_config_title: "إعدادات المحرك والتشغيل",
      badge_graceful_restart: "إعادة تشغيل رشيقة",
      lbl_profile: "بيئة التشغيل (Profile)",
      lbl_symbols: "الرموز (مفصولة بفاصلة)",
      lbl_signal_source: "مصدر الإشارات (Signal Source)",
      lbl_bar_interval: "الفاصل الزمني بين الأشرطة (ثوان)",
      lbl_n_bars: "عدد الأشرطة",
      lbl_seed: "البذرة العشوائية",
      lbl_mode: "وضع التشغيل",
      lbl_dry_run: "تشغيل جاف (Dry Run)",
      lbl_balance: "رأس المال الأولي ($)",
      btn_apply_config: "تطبيق وإعادة التشغيل الرشيقة",
      ctrl_risk_limits_title: "حدود وإدارة المخاطر (Risk Limits)",
      lbl_max_pos_pct: "أقصى حجم للمركز الواحد (%)",
      lbl_max_dd_pct: "الحد الأقصى للتراجع الكلي (%)",
      lbl_max_daily_loss: "الحد الأقصى للخسارة اليومية (%)",
      lbl_stop_dist: "المسافة الافتراضية لوقف الخسارة (%)",
      btn_save_limits: "حفظ وتطبيق حدود المخاطر",
      ctrl_live_gate_title: "بوابة التداول الحي بأموال حقيقية (Multi-Step Gate)",
      alert_live_warning_title: "تنبيه أمان صارم:",
      alert_live_warning_text: "التداول الحي بأموال حقيقية مقفل تلقائياً. لفتح هذه البوابة يلزم ضبط `PYROBOT_ALLOW_LIVE_TRADING=true` في خادم التشغيل، ثم إدخال العبارة التأكيدية الإلزامية وتأكيد الخطوة الثانية.",
      lbl_confirmation_phrase: "أدخل العبارة التأكيدية الحرفية:",
      lbl_live_step_two: "أؤكد تحمل المسؤولية الكاملة وامتثال كافة اختبارات الحساب الورقي أولاً.",
      btn_unlock_live: "فتح قفل التداول الحي (Unlock Live Profile)",
      panel_audit_title: "سجل التدقيق المشفر والمقاوم للتلاعب (Tamper-Evident Ledger)",
      th_action: "نوع العملية",
      th_details: "التفاصيل",
      th_checksum: "البصمة (Checksum)",
      btn_refresh: "تحديث",
      loading_audit: "جاري تحميل سجل التدقيق...",
      modal_login_title: "تسجيل الدخول إلى وحدة التحكم",
      lbl_auth_token: "رمز التوكن (Access Token):",
      btn_submit_login: "دخول",
      btn_cancel: "إلغاء",
      btn_confirm: "تأكيد وتنفيذ",
      tab_reports: "تقارير العمليات",
      panel_reports_title: "تقارير العمليات والتداول (Trading Operations Reports)",
      reports_hint: "تعتمد المؤشرات والمؤامرة على سجل المقاييس المثبت على القرص (runtime_metrics.jsonl) وسجل التدقيق، وتعكس آخر جلسة تشغيل مكتملة حتى عند إيقاف المحرك.",
      kpi_returns: "العائد الكلي",
      kpi_final_equity: "إجمالي المحفظة النهائي",
      kpi_max_dd: "أقصى تراجع",
      kpi_orders: "الأوامر",
      kpi_best_day: "أفضل يوم",
      kpi_worst_day: "أسوأ يوم",
      panel_report_equity: "منحنى المحفظة (Equity Curve)",
      panel_daily_perf: "الأداء اليومي (Daily Performance)",
      panel_trades: "عمليات التنفيذ الأخيرة (Recent Fills)",
      panel_backtests: "نتائج الاختبارات الخلفية (Backtest Reports)",
      th_date: "التاريخ",
      th_equity: "إجمالي المحفظة",
      th_day_return: "العائد اليومي",
      th_positions: "عدد المراكز",
      th_side_direction: "الاتجاه",
      th_fill_price: "سعر التنفيذ",
      th_source: "المصدر",
      th_report_name: "اسم التقرير",
      th_strategy: "الاستراتيجية",
      th_backtest_return: "العائد",
      th_sharpe: "Sharpe",
      th_max_dd: "أقصى تراجع",
      th_trades: "صفقات",
      th_reports_count: "عدد",
      report_empty: "لا توجد بيانات بعد.",
      report_no_data: "لا توجد بيانات كافية لتوليد تقرير بعد.",
      report_generated: "آخر تحديث",
      backtest_strategy_buy_hold: "شراء واحتفاظ",
      status_buy: "شراء",
      status_sell: "بيع",
      status_unknown: "غير معروف",
      err_action_failed: "فشل التنفيذ"
    },
    en: {
      nav_console_sub: "Command & Control Dashboard",
      tab_overview: "Overview",
      tab_control: "Control Room",
      tab_audit: "Audit Ledger",
      tab_markets: "Markets",
      btn_login: "Login / Switch",
      metric_engine_status: "Engine Status",
      metric_equity: "Account Equity",
      sub_today: "Today",
      metric_drawdown: "Drawdown",
      metric_risk_gates: "Risk Gates",
      gate_kill_switch: "Kill Switch:",
      gate_circuit_breaker: "Circuit Breaker:",
      gate_model_scale: "Model Scale:",
      chart_equity_title: "Live Equity Curve",
      freshness_label: "Data Age:",
      panel_signals_title: "Live Signal Stream",
      no_signals_yet: "No signals recorded yet...",
      panel_positions_title: "Open Positions",
      th_symbol: "Symbol",
      th_qty: "Quantity",
      th_entry_price: "Entry Price",
      th_cur_price: "Current Price",
      th_market_val: "Market Value",
      th_unrealized_pnl: "Unrealized PnL",
      no_open_positions: "No open positions currently",
      panel_orders_title: "Recent Orders",
      th_order_id: "Order ID",
      th_side: "Side",
      th_status: "Status",
      th_time: "Time",
      no_orders_yet: "No orders yet",
      control_restricted_title: "Manager Role Required",
      control_restricted_desc: "You are currently viewing in read-only mode. Login with a MANAGER token to execute control actions.",
      ctrl_lifecycle_title: "Engine Lifecycle",
      btn_start: "Start Engine",
      btn_pause: "Pause",
      btn_resume: "Resume",
      btn_stop: "Graceful Stop",
      ctrl_emergency_title: "Emergency Kill Switch",
      ctrl_kill_desc: "Activating the kill switch immediately halts all trading and rejects any new orders until manually reset.",
      btn_kill_activate: "Activate Emergency Kill Switch",
      btn_kill_reset: "Reset Kill Switch",
      ctrl_config_title: "Runtime Engine Configuration",
      badge_graceful_restart: "Graceful Restart",
      lbl_profile: "Execution Profile",
      lbl_symbols: "Symbols (comma-separated)",
      lbl_signal_source: "Signal Source",
      lbl_bar_interval: "Bar Interval (seconds)",
      lbl_n_bars: "Number of Bars",
      lbl_seed: "Random Seed",
      lbl_mode: "Run Mode",
      lbl_dry_run: "Dry Run",
      lbl_balance: "Initial Cash Balance ($)",
      btn_apply_config: "Apply & Graceful Restart",
      ctrl_risk_limits_title: "Risk Limits Management",
      lbl_max_pos_pct: "Max Position Size (%)",
      lbl_max_dd_pct: "Max Portfolio Drawdown (%)",
      lbl_max_daily_loss: "Daily Loss Limit (%)",
      lbl_stop_dist: "Default Stop Distance (%)",
      btn_save_limits: "Save & Apply Risk Limits",
      ctrl_live_gate_title: "Live Real-Money Trading Gate",
      alert_live_warning_title: "Strict Safety Lock:",
      alert_live_warning_text: "Live trading is locked by default. Unlocking requires `PYROBOT_ALLOW_LIVE_TRADING=true` on the server, exact confirmation phrase entry, and second-step verification.",
      lbl_confirmation_phrase: "Enter exact confirmation phrase:",
      lbl_live_step_two: "I confirm full responsibility and acceptance testing completion.",
      btn_unlock_live: "Unlock Live Profile",
      panel_audit_title: "Tamper-Evident Cryptographic Audit Ledger",
      th_action: "Action Type",
      th_details: "Details",
      th_checksum: "Checksum",
      btn_refresh: "Refresh",
      loading_audit: "Loading audit ledger...",
      modal_login_title: "Console Authentication",
      lbl_auth_token: "Access Token:",
      btn_submit_login: "Sign In",
      btn_cancel: "Cancel",
      btn_confirm: "Confirm & Execute",
      tab_reports: "Operations Reports",
      panel_reports_title: "Trading Operations Reports",
      reports_hint: "Indicators and charts are derived from the on-disk metrics ledger (runtime_metrics.jsonl) and audit ledger, reflecting the last completed session even while the engine is stopped.",
      kpi_returns: "Total Return",
      kpi_final_equity: "Final Equity",
      kpi_max_dd: "Max Drawdown",
      kpi_orders: "Orders",
      kpi_best_day: "Best Day",
      kpi_worst_day: "Worst Day",
      panel_report_equity: "Equity Curve",
      panel_daily_perf: "Daily Performance",
      panel_trades: "Recent Fills",
      panel_backtests: "Backtest Reports",
      th_date: "Date",
      th_equity: "Equity",
      th_day_return: "Day Return",
      th_positions: "Positions",
      th_side_direction: "Direction",
      th_fill_price: "Fill Price",
      th_source: "Source",
      th_report_name: "Report Name",
      th_strategy: "Strategy",
      th_backtest_return: "Return",
      th_sharpe: "Sharpe",
      th_max_dd: "Max Drawdown",
      th_trades: "Trades",
      th_reports_count: "Count",
      report_empty: "No data yet.",
      report_no_data: "Not enough data to produce a report yet.",
      report_generated: "Updated",
      backtest_strategy_buy_hold: "Buy & Hold",
      status_buy: "Buy",
      status_sell: "Sell",
      status_unknown: "Unknown",
      err_action_failed: "Action failed"
    }
  };

  // ── Global State ──────────────────────────────────────────────────────────
  const state = {
    lang: localStorage.getItem('pyrobot_lang') || 'ar',
    role: 'viewer',
    canControl: false,
    canAudit: false,
    overview: {},
    equityHistory: [],
    eventSource: null,
    lastPerformanceReport: null,
  };

  // ── DOM Elements ──────────────────────────────────────────────────────────
  const dom = {
    app: document.getElementById('app'),
    tabBtns: document.querySelectorAll('.tab-btn'),
    tabPanes: document.querySelectorAll('.tab-pane'),
    langSwitchBtn: document.getElementById('lang-switch-btn'),
    langLabel: document.getElementById('lang-label'),
    authBtn: document.getElementById('auth-btn'),
    currentRoleBadge: document.getElementById('current-role-badge'),
    currentRoleText: document.getElementById('current-role-text'),
    streamStatus: document.getElementById('stream-status'),
    streamStatusText: document.getElementById('stream-status-text'),

    // Overview Cards
    cardStatePill: document.getElementById('card-state-pill'),
    cardStateValue: document.getElementById('card-state-value'),
    cardProfileSub: document.getElementById('card-profile-sub'),
    cardEquity: document.getElementById('card-equity'),
    cardDailyPnl: document.getElementById('card-daily-pnl'),
    cardDrawdown: document.getElementById('card-drawdown'),
    cardMaxDdSub: document.getElementById('card-max-dd-sub'),
    cardKillSwitch: document.getElementById('card-kill-switch'),
    cardCircuitBreaker: document.getElementById('card-circuit-breaker'),
    cardModelScale: document.getElementById('card-model-scale'),
    dataFreshnessVal: document.getElementById('data-freshness-val'),
    chartBarsCount: document.getElementById('chart-bars-count'),
    equityCanvas: document.getElementById('equityCanvas'),

    // Signals & Tables
    signalsList: document.getElementById('signals-stream-list'),
    signalsCount: document.getElementById('signals-count'),
    positionsTbody: document.getElementById('positions-tbody'),
    positionsCount: document.getElementById('positions-count'),
    ordersTbody: document.getElementById('orders-tbody'),
    ordersCount: document.getElementById('orders-count'),

    // Controls
    controlRoleWarning: document.getElementById('control-role-warning'),
    ctrlStateBadge: document.getElementById('ctrl-state-badge'),
    ctrlKillBadge: document.getElementById('ctrl-kill-badge'),
    btnCtrlStart: document.getElementById('btn-ctrl-start'),
    btnCtrlPause: document.getElementById('btn-ctrl-pause'),
    btnCtrlResume: document.getElementById('btn-ctrl-resume'),
    btnCtrlStop: document.getElementById('btn-ctrl-stop'),
    btnKillActivate: document.getElementById('btn-kill-activate'),
    btnKillReset: document.getElementById('btn-kill-reset'),

    // Forms
    configForm: document.getElementById('config-form'),
    cfgProfile: document.getElementById('cfg-profile'),
    cfgSymbols: document.getElementById('cfg-symbols'),
    cfgSource: document.getElementById('cfg-source'),
    cfgInterval: document.getElementById('cfg-interval'),
    cfgBalance: document.getElementById('cfg-balance'),
    cfgNBars: document.getElementById('cfg-n-bars'),
    cfgSeed: document.getElementById('cfg-seed'),
    cfgMode: document.getElementById('cfg-mode'),
    cfgDryRun: document.getElementById('cfg-dry-run'),
    limitsForm: document.getElementById('limits-form'),
    limitMaxPos: document.getElementById('limit-max-pos'),
    limitMaxDd: document.getElementById('limit-max-dd'),
    limitDailyLoss: document.getElementById('limit-daily-loss'),
    limitStopDist: document.getElementById('limit-stop-dist'),
    liveUnlockForm: document.getElementById('live-unlock-form'),
    livePhraseInput: document.getElementById('live-phrase-input'),
    liveStepTwoCheck: document.getElementById('live-step-two-check'),
    liveGateEnvStatus: document.getElementById('live-gate-env-status'),

    // Theme & Branding
    themeForm: document.getElementById('theme-form'),
    themePlatformName: document.getElementById('theme-platform-name'),
    themePlatformSubtitle: document.getElementById('theme-platform-subtitle'),
    themeLogoUrl: document.getElementById('theme-logo-url'),
    themePrimaryColor: document.getElementById('theme-primary-color'),
    themeAccentColor: document.getElementById('theme-accent-color'),
    themeBgPrimary: document.getElementById('theme-bg-primary'),
    btnResetTheme: document.getElementById('btn-reset-theme'),

    // Audit
    auditTbody: document.getElementById('audit-tbody'),
    auditActionFilter: document.getElementById('audit-action-filter'),
    btnRefreshAudit: document.getElementById('btn-refresh-audit'),

    // Trading Operations Reports
    btnRefreshReports: document.getElementById('btn-refresh-reports'),
    rptTotalReturn: document.getElementById('rpt-total-return'),
    rptFinalEquity: document.getElementById('rpt-final-equity'),
    rptMaxDd: document.getElementById('rpt-max-dd'),
    rptTrades: document.getElementById('rpt-trades'),
    rptBestDay: document.getElementById('rpt-best-day'),
    rptWorstDay: document.getElementById('rpt-worst-day'),
    rptCurveCount: document.getElementById('rpt-curve-count'),
    reportsEquityChart: document.getElementById('reports-equity-chart'),
    reportsDailyTbody: document.getElementById('reports-daily-tbody'),
    reportsTradesTbody: document.getElementById('reports-trades-tbody'),
    reportsBacktestsTbody: document.getElementById('reports-backtests-tbody'),
    rptBacktestsCount: document.getElementById('rpt-backtests-count'),

    // Modals
    modalBackdrop: document.getElementById('modal-backdrop'),
    loginModal: document.getElementById('login-modal'),
    loginForm: document.getElementById('login-form'),
    loginTokenInput: document.getElementById('login-token-input'),
    loginModalClose: document.getElementById('login-modal-close'),
    confirmModalClose: document.getElementById('confirm-modal-close'),
    confirmModal: document.getElementById('confirm-modal'),
    confirmModalTitle: document.getElementById('confirm-modal-title'),
    confirmModalMessage: document.getElementById('confirm-modal-message'),
    btnConfirmCancel: document.getElementById('btn-confirm-cancel'),
    btnConfirmProceed: document.getElementById('btn-confirm-proceed'),
    toastContainer: document.getElementById('toast-container'),
  };

  // ── Localization Engine ───────────────────────────────────────────────────
  function applyLanguage(lang) {
    state.lang = lang;
    localStorage.setItem('pyrobot_lang', lang);
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr';
    dom.langLabel.textContent = lang === 'ar' ? 'EN' : 'عربي';

    const dict = I18N[lang] || I18N.ar;
    document.querySelectorAll('[data-i18n]').forEach((el) => {
      const key = el.getAttribute('data-i18n');
      if (dict[key]) {
        el.textContent = dict[key];
      }
    });

    renderEquityChart();
  }

  function toggleLanguage() {
    applyLanguage(state.lang === 'ar' ? 'en' : 'ar');
  }

  // ── Toast Notifications ───────────────────────────────────────────────────
  function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    dom.toastContainer.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      setTimeout(() => toast.remove(), 300);
    }, 3500);
  }

  // ── API Helpers ───────────────────────────────────────────────────────────
  // `options.silent` suppresses the auto-login-modal for background loads
  // (polling, initial data, theme) so anonymous viewers are not hijacked by
  // repeated 401 responses. User-initiated actions keep the modal behavior.
  async function apiFetch(endpoint, options = {}) {
    const defaultHeaders = {
      'Content-Type': 'application/json',
    };
    try {
      const res = await fetch(endpoint, {
        ...options,
        headers: { ...defaultHeaders, ...(options.headers || {}) },
      });
      if (res.status === 401 && !options.silent) {
        openLoginModal();
      }
      return res;
    } catch (err) {
      showToast(`Network error: ${err.message}`, 'error');
      throw err;
    }
  }

  // Extract a user-readable message from a failed API response ({detail}).
  async function formatApiError(res, fallback) {
    const fallbackText = fallback || (state.lang === 'ar' ? 'فشل التنفيذ' : 'Action failed');
    try {
      if (!res || !res.ok) {
        const data = await res.json();
        const msg =
          data?.detail ||
          data?.message ||
          data?.error ||
          data?.statusText ||
          (typeof data === 'string' ? data : null);
        return msg ? `${fallbackText}: ${msg}` : fallbackText;
      }
    } catch {
      // Body was already consumed or not JSON — fall back to a generic message.
    }
    return fallbackText;
  }

  async function refreshAuthoritativeOverview() {
    const res = await apiFetch('/api/overview', { silent: true });
    if (res.ok) {
      updateOverviewUI(await res.json());
    }
  }

  // ── Tab Management ────────────────────────────────────────────────────────
  function initTabs() {
    dom.tabBtns.forEach((btn) => {
      btn.addEventListener('click', () => {
        const tab = btn.getAttribute('data-tab');
        dom.tabBtns.forEach((b) => b.classList.remove('active'));
        dom.tabPanes.forEach((p) => p.classList.remove('active'));
        btn.classList.add('active');
        const targetPane = document.getElementById(`pane-${tab}`);
        if (targetPane) targetPane.classList.add('active');

        if (tab === 'audit') loadAuditLogs();
        if (tab === 'control') { loadRiskLimits(); loadEngineConfig(); }
        if (tab === 'overview') renderEquityChart();
        if (tab === 'reports') loadReports();
      });
    });
  }

  // Re-fetch data for whichever pane is currently visible (used after login
  // so role-gated panels fill in without forcing a manual page reload).
  function refreshActiveTabData() {
    const active = document.querySelector('.tab-btn.active');
    const tab = active ? active.getAttribute('data-tab') : 'overview';
    if (tab === 'audit') loadAuditLogs();
    if (tab === 'control') { loadRiskLimits(); loadEngineConfig(); }
    if (tab === 'reports') loadReports();
    refreshAuthoritativeOverview();
  }

  // ── Authentication & Roles ────────────────────────────────────────────────
  async function checkAuth() {
    try {
      const res = await apiFetch('/api/auth/me', { silent: true });
      if (res.ok) {
        const data = await res.json();
        state.role = data.role;
        state.canControl = data.can_control;
        state.canAudit = data.can_audit;
        updateRoleUI();
      } else {
        state.role = 'viewer';
        state.canControl = false;
        state.canAudit = false;
        updateRoleUI();
      }
    } catch {
      state.role = 'viewer';
      updateRoleUI();
    }
  }

  function updateRoleUI() {
    dom.currentRoleText.textContent = state.role.toUpperCase();
    if (state.role === 'manager') {
      dom.currentRoleBadge.style.borderColor = 'var(--success)';
      dom.currentRoleBadge.style.color = 'var(--success)';
    } else if (state.role === 'dev') {
      dom.currentRoleBadge.style.borderColor = 'var(--accent-blue)';
      dom.currentRoleBadge.style.color = '#93c5fd';
    } else {
      dom.currentRoleBadge.style.borderColor = 'var(--text-muted)';
      dom.currentRoleBadge.style.color = 'var(--text-muted)';
    }

    if (dom.controlRoleWarning) {
      dom.controlRoleWarning.style.display = state.canControl ? 'none' : 'flex';
    }

    // Disable control buttons if not manager
    const ctrlInputs = [
      dom.btnCtrlStart, dom.btnCtrlPause, dom.btnCtrlResume, dom.btnCtrlStop,
      dom.btnKillActivate, dom.btnKillReset,
      document.getElementById('btn-save-config'),
      document.getElementById('btn-save-limits'),
      document.getElementById('btn-live-unlock'),
    ];
    ctrlInputs.forEach((el) => {
      if (el) el.disabled = !state.canControl;
    });
  }

  function openLoginModal() {
    dom.modalBackdrop.style.display = 'flex';
    dom.loginModal.style.display = 'block';
    dom.confirmModal.style.display = 'none';
  }

  function closeModals() {
    dom.modalBackdrop.style.display = 'none';
    dom.loginModal.style.display = 'none';
    dom.confirmModal.style.display = 'none';
  }

  // ── Confirmation Dialog Helper ────────────────────────────────────────────
  let pendingConfirmAction = null;

  function showConfirmDialog(title, message, onConfirm) {
    dom.confirmModalTitle.textContent = title;
    dom.confirmModalMessage.textContent = message;
    pendingConfirmAction = onConfirm;
    dom.modalBackdrop.style.display = 'flex';
    dom.confirmModal.style.display = 'block';
    dom.loginModal.style.display = 'none';
  }

  // ── SSE Streaming & Overview ──────────────────────────────────────────────
  function initSSE() {
    if (state.eventSource) {
      state.eventSource.close();
    }

    state.eventSource = new EventSource('/api/stream');

    state.eventSource.onopen = () => {
      dom.streamStatus.style.borderColor = 'rgba(16, 185, 129, 0.3)';
      dom.streamStatusText.textContent = 'LIVE SSE';
    };

    state.eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        updateOverviewUI(data);
      } catch (err) {
        console.error('Failed to parse SSE payload', err);
      }
    };

    state.eventSource.onerror = () => {
      dom.streamStatus.style.borderColor = 'rgba(239, 68, 68, 0.4)';
      dom.streamStatusText.textContent = 'OFFLINE';
    };
  }

  function updateOverviewUI(data) {
    state.overview = data;

    // Engine State
    const st = (data.state || 'STOPPED').toUpperCase();
    dom.cardStateValue.textContent = st;
    dom.cardStatePill.textContent = st;
    dom.cardStatePill.className = `status-indicator-pill ${st.toLowerCase()}`;
    if (dom.ctrlStateBadge) {
      dom.ctrlStateBadge.textContent = st;
      dom.ctrlStateBadge.className = `status-indicator-pill ${st.toLowerCase()}`;
    }
    dom.cardProfileSub.textContent = `Profile: ${data.profile || 'Replay'} (${data.signal_source || 'Example'})`;

    // Equity & PnL
    const eq = Number(data.equity || 100000);
    dom.cardEquity.textContent = `$${eq.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

    const pnl = Number(data.daily_pnl || 0);
    const pnlPct = Number(data.daily_loss_pct || 0);
    const isPos = pnl >= 0;
    dom.cardDailyPnl.innerHTML = `
      <span class="pnl-tag font-mono ${isPos ? 'positive' : 'negative'}">
        ${isPos ? '+' : ''}${pnl.toFixed(2)} (${isPos ? '+' : ''}${(pnlPct * 100).toFixed(2)}%)
      </span>
      <span class="text-muted">${I18N[state.lang].sub_today}</span>
    `;

    // Drawdown
    const dd = Number(data.drawdown || 0);
    dom.cardDrawdown.textContent = `${(dd * 100).toFixed(2)}%`;
    dom.cardMaxDdSub.textContent = `Bars Processed: ${data.bars_processed || 0}`;

    // Risk Gates
    const killActive = !!data.kill_switch_active;
    dom.cardKillSwitch.textContent = killActive ? 'ACTIVE' : 'INACTIVE';
    dom.cardKillSwitch.className = `badge ${killActive ? 'badge-danger' : 'badge-success'}`;
    if (dom.ctrlKillBadge) {
      dom.ctrlKillBadge.textContent = killActive ? 'ACTIVE' : 'INACTIVE';
      dom.ctrlKillBadge.className = `badge ${killActive ? 'badge-danger' : 'badge-success'}`;
    }

    const cbState = (data.circuit_breaker && data.circuit_breaker.state) || 'CLOSED';
    const cbScale = (data.circuit_breaker && data.circuit_breaker.scale) || 1.0;
    dom.cardCircuitBreaker.textContent = `${cbState} (${cbScale}x)`;
    dom.cardCircuitBreaker.className = `badge ${cbState === 'CLOSED' ? 'badge-neutral' : 'badge-warning'}`;

    const modelScale = Number(data.model_risk_scale || 1.0);
    dom.cardModelScale.textContent = `${modelScale}x`;

    // Data Freshness
    if (data.data_freshness && Object.keys(data.data_freshness).length > 0) {
      const firstSym = Object.keys(data.data_freshness)[0];
      const age = data.data_freshness[firstSym].age_seconds;
      dom.dataFreshnessVal.textContent = age !== null ? `${age}s (${firstSym})` : 'N/A';
    } else {
      dom.dataFreshnessVal.textContent = '0.0s';
    }

    dom.chartBarsCount.textContent = `${data.bars_processed || 0} bars`;

    // Track equity curve
    if (state.equityHistory.length === 0 || state.equityHistory[state.equityHistory.length - 1].equity !== eq) {
      state.equityHistory.push({
        time: new Date().toLocaleTimeString(),
        equity: eq,
      });
      if (state.equityHistory.length > 60) state.equityHistory.shift();
      renderEquityChart();
    }

    // Refresh child tables (throttled — SSE pushes every ~2s and each message
    // would otherwise trigger three API calls in a row).
    refreshChildTables();
  }

  let childTablesLastFetch = 0;
  function refreshChildTables(force = false) {
    const now = Date.now();
    if (!force && now - childTablesLastFetch < 2000) return;
    childTablesLastFetch = now;
    loadPositions();
    loadOrders();
    loadSignals();
  }

  // ── Custom Canvas 2D Equity Chart (Zero Dependency) ───────────────────────
  function renderEquityChart() {
    const canvas = dom.equityCanvas;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const width = (canvas.width = canvas.parentElement.clientWidth);
    const height = (canvas.height = canvas.parentElement.clientHeight);

    ctx.clearRect(0, 0, width, height);

    const history = state.equityHistory;
    if (history.length < 2) {
      ctx.fillStyle = '#64748b';
      ctx.font = '13px JetBrains Mono, monospace';
      ctx.textAlign = 'center';
      ctx.fillText(state.lang === 'ar' ? 'جاري استقبال تدفق البيانات...' : 'Waiting for real-time telemetry...', width / 2, height / 2);
      return;
    }

    const values = history.map((h) => h.equity);
    const minVal = Math.min(...values) * 0.9995;
    const maxVal = Math.max(...values) * 1.0005;
    const padding = { top: 20, right: 30, bottom: 25, left: 65 };
    const chartW = width - padding.left - padding.right;
    const chartH = height - padding.top - padding.bottom;

    // Draw Grid Lines
    ctx.strokeStyle = '#1e293b';
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
      const y = padding.top + (chartH / 4) * i;
      ctx.beginPath();
      ctx.moveTo(padding.left, y);
      ctx.lineTo(width - padding.right, y);
      ctx.stroke();

      const price = maxVal - ((maxVal - minVal) / 4) * i;
      ctx.fillStyle = '#64748b';
      ctx.font = '10px JetBrains Mono, monospace';
      ctx.textAlign = 'right';
      ctx.fillText(`$${price.toFixed(1)}`, padding.left - 8, y + 3);
    }

    // Compute Points
    const points = history.map((h, i) => {
      const x = padding.left + (chartW / (history.length - 1)) * i;
      const y = padding.top + chartH - ((h.equity - minVal) / (maxVal - minVal)) * chartH;
      return { x, y };
    });

    // Fill Gradient Area
    const grad = ctx.createLinearGradient(0, padding.top, 0, height - padding.bottom);
    grad.addColorStop(0, 'rgba(59, 130, 246, 0.35)');
    grad.addColorStop(1, 'rgba(59, 130, 246, 0.0)');

    ctx.beginPath();
    ctx.moveTo(points[0].x, points[0].y);
    points.forEach((p) => ctx.lineTo(p.x, p.y));
    ctx.lineTo(points[points.length - 1].x, height - padding.bottom);
    ctx.lineTo(points[0].x, height - padding.bottom);
    ctx.closePath();
    ctx.fillStyle = grad;
    ctx.fill();

    // Draw Line
    ctx.beginPath();
    ctx.strokeStyle = '#3b82f6';
    ctx.lineWidth = 2.5;
    ctx.lineJoin = 'round';
    ctx.moveTo(points[0].x, points[0].y);
    points.forEach((p) => ctx.lineTo(p.x, p.y));
    ctx.stroke();

    // Draw Last Point Pulse
    const lastP = points[points.length - 1];
    ctx.beginPath();
    ctx.arc(lastP.x, lastP.y, 4, 0, Math.PI * 2);
    ctx.fillStyle = '#06b6d4';
    ctx.fill();
    ctx.strokeStyle = '#ffffff';
    ctx.lineWidth = 1.5;
    ctx.stroke();
  }

  // ── Tables Loading ────────────────────────────────────────────────────────
  async function loadPositions() {
    try {
      const res = await apiFetch('/api/positions', { silent: true });
      if (!res.ok) return;
      const positions = await res.json();
      dom.positionsCount.textContent = positions.length;

      if (positions.length === 0) {
        dom.positionsTbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted">${I18N[state.lang].no_open_positions}</td></tr>`;
        return;
      }

      dom.positionsTbody.innerHTML = positions.map((p) => {
        const isPos = p.unrealized_pnl >= 0;
        return `
          <tr>
            <td class="font-mono font-bold">${p.symbol}</td>
            <td class="font-mono">${p.quantity}</td>
            <td class="font-mono">$${p.entry_price.toFixed(2)}</td>
            <td class="font-mono">$${p.current_price.toFixed(2)}</td>
            <td class="font-mono">$${p.market_value.toFixed(2)}</td>
            <td class="font-mono ${isPos ? 'text-success' : 'text-danger'} font-bold">
              ${isPos ? '+' : ''}${p.unrealized_pnl.toFixed(2)} (${isPos ? '+' : ''}${p.unrealized_pnl_pct.toFixed(2)}%)
            </td>
          </tr>
        `;
      }).join('');
    } catch { }
  }

  async function loadOrders() {
    try {
      const res = await apiFetch('/api/orders', { silent: true });
      if (!res.ok) return;
      const orders = await res.json();
      dom.ordersCount.textContent = orders.length;

      if (orders.length === 0) {
        dom.ordersTbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted">${I18N[state.lang].no_orders_yet}</td></tr>`;
        return;
      }

      dom.ordersTbody.innerHTML = orders.slice(0, 15).map((o) => {
        const sideColor = o.side === 'BUY' ? 'text-success' : 'text-danger';
        const stBadge = o.state === 'FILLED' ? 'badge-success' : o.state === 'REJECTED' ? 'badge-danger' : 'badge-neutral';
        const timeStr = o.submitted_at ? new Date(o.submitted_at).toLocaleTimeString() : '-';
        return `
          <tr>
            <td class="font-mono text-xs text-muted">${(o.client_order_id || '').slice(-8)}</td>
            <td class="font-mono font-bold">${o.symbol}</td>
            <td class="font-mono font-bold ${sideColor}">${o.side}</td>
            <td class="font-mono">${o.quantity}</td>
            <td><span class="badge ${stBadge}">${o.state}</span></td>
            <td class="font-mono text-xs text-muted">${timeStr}</td>
          </tr>
        `;
      }).join('');
    } catch { }
  }

  async function loadSignals() {
    try {
      const res = await apiFetch('/api/signals?limit=15', { silent: true });
      if (!res.ok) return;
      const signals = await res.json();
      dom.signalsCount.textContent = signals.length;

      if (signals.length === 0) {
        dom.signalsList.innerHTML = `<div class="empty-state text-muted">${I18N[state.lang].no_signals_yet}</div>`;
        return;
      }

      dom.signalsList.innerHTML = signals.slice(-10).reverse().map((sig) => {
        const action = sig.details ? sig.details.action || 'NO_TRADE' : 'NO_TRADE';
        const sym = sig.symbol || (sig.details && sig.details.symbol) || '-';
        const prob = sig.details && sig.details.probability !== undefined ? (sig.details.probability * 100).toFixed(1) + '%' : '';
        const time = sig.timestamp ? new Date(sig.timestamp).toLocaleTimeString() : '';
        return `
          <div class="signal-card">
            <div style="display:flex; align-items:center; gap:0.5rem;">
              <span class="signal-action ${action}">${action}</span>
              <span class="font-mono font-bold">${sym}</span>
            </div>
            <div style="display:flex; align-items:center; gap:0.5rem;">
              <span class="font-mono text-xs text-highlight">${prob}</span>
              <span class="font-mono text-xs text-muted">${time}</span>
            </div>
          </div>
        `;
      }).join('');
    } catch { }
  }

  // ── Audit Logs ────────────────────────────────────────────────────────────
  async function loadAuditLogs() {
    try {
      const filter = dom.auditActionFilter ? dom.auditActionFilter.value : '';
      const url = filter ? `/api/audit?action=${encodeURIComponent(filter)}&limit=50` : '/api/audit?limit=50';
      const res = await apiFetch(url, { silent: true });
      if (!res.ok) {
        dom.auditTbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted">Permission denied (DEV/MANAGER role required)</td></tr>`;
        return;
      }
      const events = await res.json();
      if (events.length === 0) {
        dom.auditTbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted">No audit events found</td></tr>`;
        return;
      }

      dom.auditTbody.innerHTML = events.reverse().map((e) => {
        const actionBadge = e.action === 'KILL_SWITCH_TRIGGERED' ? 'badge-danger' : e.action === 'CONTROL_ACTION' ? 'badge-primary' : 'badge-neutral';
        const checksumShort = (e.checksum || '').slice(0, 10);
        return `
          <tr>
            <td>#${e.event_id}</td>
            <td class="text-xs text-muted">${e.timestamp ? e.timestamp.replace('T', ' ').slice(0, 19) : ''}</td>
            <td><span class="badge ${actionBadge}">${e.action}</span></td>
            <td>${e.symbol || '-'}</td>
            <td class="text-xs text-muted">${JSON.stringify(e.details || {}).slice(0, 70)}...</td>
            <td class="text-xs text-highlight" title="${e.checksum}">${checksumShort}…</td>
          </tr>
        `;
      }).join('');
    } catch { }
  }

  // ── Risk Limits & Configuration ───────────────────────────────────────────
  async function loadRiskLimits() {
    try {
      const res = await apiFetch('/api/control/risk-limits', { silent: true });
      if (res.ok) {
        const limits = await res.json();
        // Field names follow the RiskLimits schema returned by the server.
        dom.limitMaxPos.value = limits.max_position_size_pct ?? 0.10;
        dom.limitMaxDd.value = limits.max_drawdown_pct ?? 0.15;
        dom.limitDailyLoss.value = limits.max_daily_loss_pct ?? 0.03;
        dom.limitStopDist.value = limits.default_stop_distance_pct ?? 0.02;
      }
    } catch { }
  }

  // Prefill the engine config form from the persisted config (Manager).
  async function loadEngineConfig() {
    try {
      const res = await apiFetch('/api/control/config', { silent: true });
      if (!res.ok) return;
      const cfg = await res.json();
      if (cfg.profile) dom.cfgProfile.value = cfg.profile;
      if (Array.isArray(cfg.symbols)) dom.cfgSymbols.value = cfg.symbols.join(', ');
      if (cfg.signal_source) dom.cfgSource.value = cfg.signal_source;
      if (cfg.bar_interval) dom.cfgInterval.value = cfg.bar_interval;
      if (cfg.initial_balance) dom.cfgBalance.value = cfg.initial_balance;
      if (cfg.n_bars !== undefined) dom.cfgNBars.value = cfg.n_bars;
      if (cfg.seed !== undefined) dom.cfgSeed.value = cfg.seed;
      if (cfg.mode) dom.cfgMode.value = cfg.mode;
      if (cfg.dry_run !== undefined) dom.cfgDryRun.checked = cfg.dry_run;
    } catch { }
  }

  // ── Trading Operations Reports ────────────────────────────────────────────
  function fmtMoney(v) {
    return `$${Number(v || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }

  function fmtPct(v, digits = 2) {
    const n = Number(v);
    if (!Number.isFinite(n)) return '--';
    return `${n >= 0 ? '+' : ''}${n.toFixed(digits)}%`;
  }

  function emptyRow(colspan, tbody, key) {
    tbody.innerHTML = `<tr><td colspan="${colspan}" class="text-center text-muted">${I18N[state.lang][key] || I18N[state.lang].report_empty}</td></tr>`;
  }

  async function loadReports() {
    await Promise.all([loadPerformanceReport(), loadBacktests()]);
  }

  async function loadPerformanceReport() {
    try {
      const res = await apiFetch('/api/reports/performance', { silent: true });
      if (!res.ok) return;
      const report = await res.json();
      state.lastPerformanceReport = report;
      renderPerformanceReport(report);
    } catch { }
  }

  function renderPerformanceReport(report) {
    const t = I18N[state.lang];
    const s = report.summary || {};

    if (!report.report_available) {
      dom.rptTotalReturn.textContent = '--';
      dom.rptFinalEquity.textContent = '--';
      dom.rptMaxDd.textContent = '--';
      dom.rptTrades.textContent = '--';
      dom.rptBestDay.textContent = '--';
      dom.rptWorstDay.textContent = '--';
      dom.rptCurveCount.textContent = '--';
      emptyRow(4, dom.reportsDailyTbody, 'report_no_data');
      emptyRow(6, dom.reportsTradesTbody, 'report_no_data');
      dom.reportsEquityChart.getContext('2d').clearRect(0, 0, dom.reportsEquityChart.width, dom.reportsEquityChart.height);
      return;
    }

    dom.rptTotalReturn.textContent = fmtPct(s.total_return_pct);
    dom.rptTotalReturn.className = `kpi-value font-mono ${(s.total_return_pct || 0) >= 0 ? 'text-success' : 'text-danger'}`;
    dom.rptFinalEquity.textContent = fmtMoney(s.final_equity);
    dom.rptMaxDd.textContent = `${Number(s.max_drawdown_pct || 0).toFixed(2)}%`;
    dom.rptTrades.textContent = `${s.total_orders ?? 0}`;
    dom.rptBestDay.textContent = fmtPct(s.best_day_pct);
    dom.rptWorstDay.textContent = fmtPct(s.worst_day_pct);
    dom.rptCurveCount.textContent = report.generated_at
      ? `${t.report_generated}: ${new Date(report.generated_at).toLocaleString()}`
      : '--';

    renderReportsEquityChart(report.equity_curve || []);
    renderDailyPerformance(report.daily_performance || []);
    renderTrades(report.trades || []);
  }

  function renderDailyPerformance(rows) {
    if (!rows.length) {
      emptyRow(4, dom.reportsDailyTbody, 'report_empty');
      return;
    }
    dom.reportsDailyTbody.innerHTML = rows.slice(-30).reverse().map((r) => {
      const ret = r.return_pct;
      const retCls = ret === null ? 'text-muted' : ret >= 0 ? 'text-success' : 'text-danger';
      const retTxt = ret === null ? '--' : fmtPct(ret);
      const posCount = r.positions ? Object.keys(r.positions).length : 0;
      return `
        <tr>
          <td class="font-mono">${r.date}</td>
          <td class="font-mono">${fmtMoney(r.equity)}</td>
          <td class="font-mono font-bold ${retCls}">${retTxt}</td>
          <td class="font-mono">${posCount}</td>
        </tr>
      `;
    }).join('');
  }

  function renderTrades(rows) {
    const t = I18N[state.lang];
    if (!rows.length) {
      emptyRow(6, dom.reportsTradesTbody, 'report_empty');
      return;
    }
    dom.reportsTradesTbody.innerHTML = rows.map((r) => {
      const rawSide = String(r.side || '').toUpperCase();
      let side = t.status_unknown;
      if (rawSide === 'BUY' || rawSide === 'BUY_TO_COVER') side = t.status_buy;
      else if (rawSide === 'SELL' || rawSide === 'SELL_SHORT') side = t.status_sell;
      const qty = r.quantity === null || r.quantity === undefined ? '--' : r.quantity;
      const price = r.fill_price === null || r.fill_price === undefined ? '--' : `$${Number(r.fill_price).toFixed(2)}`;
      const partial = r.partial ? ' (partial)' : '';
      return `
        <tr>
          <td class="font-mono">${(r.timestamp || '').replace('T', ' ').slice(0, 19)}</td>
          <td class="font-mono font-bold">${r.symbol || '--'}</td>
          <td class="font-mono">${side}${partial}</td>
          <td class="font-mono">${qty}</td>
          <td class="font-mono">${price}</td>
          <td class="font-mono">${r.source || '--'}</td>
        </tr>
      `;
    }).join('');
  }

  // Canvas 2D line chart for the report equity curve (zero dependency).
  function renderReportsEquityChart(curve) {
    const canvas = dom.reportsEquityChart;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const width = (canvas.width = canvas.parentElement.clientWidth);
    const height = (canvas.height = canvas.parentElement.clientHeight);

    ctx.clearRect(0, 0, width, height);

    if (!curve || curve.length < 2) {
      ctx.fillStyle = '#64748b';
      ctx.font = '13px JetBrains Mono, monospace';
      ctx.textAlign = 'center';
      ctx.fillText(I18N[state.lang].report_no_data, width / 2, height / 2);
      return;
    }

    const values = curve.map((c) => Number(c.equity || 0));
    const minVal = Math.min(...values) * 0.9995;
    const maxVal = Math.max(...values) * 1.0005;
    const padding = { top: 20, right: 30, bottom: 25, left: 70 };
    const chartW = width - padding.left - padding.right;
    const chartH = height - padding.top - padding.bottom;

    // Grid + Y axis labels
    ctx.strokeStyle = '#1e293b';
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
      const y = padding.top + (chartH / 4) * i;
      ctx.beginPath();
      ctx.moveTo(padding.left, y);
      ctx.lineTo(width - padding.right, y);
      ctx.stroke();
      const val = maxVal - ((maxVal - minVal) / 4) * i;
      ctx.fillStyle = '#64748b';
      ctx.font = '10px JetBrains Mono, monospace';
      ctx.textAlign = 'right';
      ctx.fillText(`$${val.toFixed(0)}`, padding.left - 8, y + 3);
    }

    const points = curve.map((c, i) => {
      const x = padding.left + (chartW / (curve.length - 1)) * i;
      const y = padding.top + chartH - ((Number(c.equity) - minVal) / (maxVal - minVal)) * chartH;
      return { x, y };
    });

    // Area fill
    const grad = ctx.createLinearGradient(0, padding.top, 0, height - padding.bottom);
    grad.addColorStop(0, 'rgba(6, 182, 212, 0.35)');
    grad.addColorStop(1, 'rgba(6, 182, 212, 0.0)');
    ctx.beginPath();
    ctx.moveTo(points[0].x, points[0].y);
    points.forEach((p) => ctx.lineTo(p.x, p.y));
    ctx.lineTo(points[points.length - 1].x, height - padding.bottom);
    ctx.lineTo(points[0].x, height - padding.bottom);
    ctx.closePath();
    ctx.fillStyle = grad;
    ctx.fill();

    // Line
    ctx.beginPath();
    ctx.strokeStyle = '#06b6d4';
    ctx.lineWidth = 2.5;
    ctx.lineJoin = 'round';
    ctx.moveTo(points[0].x, points[0].y);
    points.forEach((p) => ctx.lineTo(p.x, p.y));
    ctx.stroke();

    // End point pulse
    const lastP = points[points.length - 1];
    ctx.beginPath();
    ctx.arc(lastP.x, lastP.y, 4, 0, Math.PI * 2);
    ctx.fillStyle = '#3b82f6';
    ctx.fill();
    ctx.strokeStyle = '#ffffff';
    ctx.lineWidth = 1.5;
    ctx.stroke();
  }

  async function loadBacktests() {
    try {
      const res = await apiFetch('/api/reports/backtests', { silent: true });
      if (!res.ok) return;
      const data = await res.json();
      renderBacktests(data.reports || []);
    } catch { }
  }

  function renderBacktests(reports) {
    const t = I18N[state.lang];
    dom.rptBacktestsCount.textContent = reports.length;
    if (!reports.length) {
      emptyRow(7, dom.reportsBacktestsTbody, 'report_empty');
      return;
    }
    dom.reportsBacktestsTbody.innerHTML = reports.slice().reverse().map((r) => {
      const sum = r.summary || {};
      const name = (r.file || r.name || '').replace(/\.json$/, '');
      const strategy = (r.strategy || sum.strategy || '--');
      const ret = fmtPct(sum.total_return_pct);
      const retCls = (sum.total_return_pct || 0) >= 0 ? 'text-success' : 'text-danger';
      const sharp = Number(sum.sharpe);
      const sharpTxt = Number.isFinite(sharp) ? sharp.toFixed(4) : '--';
      const maxDd = sum.max_drawdown_pct === null || sum.max_drawdown_pct === undefined ? '--' : `${Number(sum.max_drawdown_pct).toFixed(2)}%`;
      const trades = sum.trades === null || sum.trades === undefined ? '--' : Number(sum.trades);
      const numReports = r.reports_count || sum.reports_count || '--';
      return `
        <tr>
          <td class="font-mono">${name}</td>
          <td class="font-mono">${strategy}</td>
          <td class="font-mono font-bold ${retCls}">${ret}</td>
          <td class="font-mono">${sharpTxt}</td>
          <td class="font-mono">${maxDd}</td>
          <td class="font-mono">${trades}</td>
          <td class="font-mono">${numReports}</td>
        </tr>
      `;
    }).join('');
  }

  // ── Event Listeners Setup ─────────────────────────────────────────────────
  function initEventListeners() {
    // Language Toggle
    dom.langSwitchBtn.addEventListener('click', toggleLanguage);

    // Auth Button & Modal
    dom.authBtn.addEventListener('click', openLoginModal);
    dom.loginModalClose.addEventListener('click', closeModals);
    dom.confirmModalClose.addEventListener('click', closeModals);
    dom.btnConfirmCancel.addEventListener('click', closeModals);

    // Hint Tokens
    document.querySelectorAll('.btn-token-hint').forEach((btn) => {
      btn.addEventListener('click', () => {
        dom.loginTokenInput.value = btn.getAttribute('data-tok');
      });
    });

    // Login Form Submit
    dom.loginForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const token = dom.loginTokenInput.value.trim();
      const res = await apiFetch('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ token }),
      });
      if (res.ok) {
        showToast(state.lang === 'ar' ? 'تم تسجيل الدخول بنجاح' : 'Login successful', 'success');
        closeModals();
        await checkAuth();
        refreshActiveTabData();
      } else {
        showToast(state.lang === 'ar' ? 'رمز وصول غير صالح' : 'Invalid access token', 'error');
      }
    });

    // Modal Confirmation Proceed
    dom.btnConfirmProceed.addEventListener('click', () => {
      if (pendingConfirmAction) {
        pendingConfirmAction();
        pendingConfirmAction = null;
      }
      closeModals();
    });

    // Engine Lifecycle Buttons
    dom.btnCtrlStart.addEventListener('click', async () => {
      const res = await apiFetch('/api/control/start', { method: 'POST' });
      if (res.ok) {
        showToast(state.lang === 'ar' ? 'تم تشغيل المحرك' : 'Engine started', 'success');
        await refreshAuthoritativeOverview();
      } else {
        showToast(await formatApiError(res, state.lang === 'ar' ? 'تعذر تشغيل المحرك' : 'Failed to start engine'), 'error');
      }
    });

    dom.btnCtrlPause.addEventListener('click', async () => {
      const res = await apiFetch('/api/control/pause', { method: 'POST' });
      if (res.ok) {
        showToast(state.lang === 'ar' ? 'تم إيقاف المحرك مؤقتاً' : 'Engine paused', 'warning');
        await refreshAuthoritativeOverview();
      } else {
        showToast(await formatApiError(res, state.lang === 'ar' ? 'تعذر الإيقاف المؤقت' : 'Failed to pause engine'), 'error');
      }
    });

    dom.btnCtrlResume.addEventListener('click', async () => {
      const res = await apiFetch('/api/control/resume', { method: 'POST' });
      if (res.ok) {
        showToast(state.lang === 'ar' ? 'تم استئناف المحرك' : 'Engine resumed', 'success');
        await refreshAuthoritativeOverview();
      } else {
        showToast(await formatApiError(res, state.lang === 'ar' ? 'تعذر الاستئناف' : 'Failed to resume engine'), 'error');
      }
    });

    dom.btnCtrlStop.addEventListener('click', () => {
      showConfirmDialog(
        state.lang === 'ar' ? 'إيقاف المحرك' : 'Stop Engine',
        state.lang === 'ar' ? 'هل أنت متأكد من إيقاف حلقة التداول رشيقة؟' : 'Are you sure you want to gracefully stop the trading loop?',
        async () => {
          const res = await apiFetch('/api/control/stop', { method: 'POST' });
          if (res.ok) {
            showToast(state.lang === 'ar' ? 'تم إيقاف المحرك برشاقة' : 'Engine stopped gracefully', 'info');
            await refreshAuthoritativeOverview();
          } else {
            showToast(await formatApiError(res, state.lang === 'ar' ? 'تعذر إيقاف المحرك' : 'Failed to stop engine'), 'error');
          }
        }
      );
    });

    // Kill Switch Buttons
    dom.btnKillActivate.addEventListener('click', () => {
      showConfirmDialog(
        state.lang === 'ar' ? 'تفعيل مفتاح الطوارئ 🚨' : 'Activate Emergency Kill Switch 🚨',
        state.lang === 'ar' ? 'تحذير: سيتم إيقاف كافة التداولات فوراً ورفض أي أوامر جديدة!' : 'Warning: All trading will be halted immediately and new orders rejected!',
        async () => {
          const res = await apiFetch('/api/control/kill-switch/activate', {
            method: 'POST',
            body: JSON.stringify({ reason: 'OPERATOR_PANIC', confirmed: true }),
          });
          if (res.ok) {
            showToast(state.lang === 'ar' ? 'تم تفعيل مفتاح الطوارئ' : 'Kill switch activated!', 'error');
            await refreshAuthoritativeOverview();
          } else {
            showToast(await formatApiError(res, state.lang === 'ar' ? 'تعذر تفعيل مفتاح الطوارئ' : 'Failed to activate kill switch'), 'error');
          }
        }
      );
    });

    dom.btnKillReset.addEventListener('click', () => {
      showConfirmDialog(
        state.lang === 'ar' ? 'إعادة ضبط مفتاح الطوارئ' : 'Reset Kill Switch',
        state.lang === 'ar' ? 'هل أنت متأكد من إعادة الضبط واستئناف إمكانية قبول الأوامر؟' : 'Are you sure you want to reset the kill switch and resume order acceptance?',
        async () => {
          const res = await apiFetch('/api/control/kill-switch/reset', {
            method: 'POST',
            body: JSON.stringify({ reason: 'OPERATOR_RESET', confirmed: true }),
          });
          if (res.ok) {
            showToast(state.lang === 'ar' ? 'تم إعادة ضبط مفتاح الطوارئ' : 'Kill switch reset', 'success');
            await refreshAuthoritativeOverview();
          } else {
            showToast(await formatApiError(res, state.lang === 'ar' ? 'تعذر إعادة الضبط' : 'Failed to reset kill switch'), 'error');
          }
        }
      );
    });

    // Config Form Submit
    dom.configForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const payload = {
        profile: dom.cfgProfile.value,
        symbols: dom.cfgSymbols.value.split(',').map((s) => s.trim().toUpperCase()),
        signal_source: dom.cfgSource.value,
        bar_interval: parseFloat(dom.cfgInterval.value),
        n_bars: parseInt(dom.cfgNBars.value, 10),
        seed: parseInt(dom.cfgSeed.value, 10),
        initial_balance: parseFloat(dom.cfgBalance.value),
        mode: dom.cfgMode.value,
        dry_run: dom.cfgDryRun.checked,
      };
      const res = await apiFetch('/api/control/config', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        showToast(state.lang === 'ar' ? 'تم تطبيق الإعدادات مع إعادة تشغيل رشيقة' : 'Configuration applied with graceful restart', 'success');
        await loadEngineConfig();
        const overviewRes = await apiFetch('/api/overview', { silent: true });
        if (overviewRes.ok) updateOverviewUI(await overviewRes.json());
      } else {
        showToast(await formatApiError(res, state.lang === 'ar' ? 'تعذر تطبيق الإعدادات' : 'Failed to apply configuration'), 'error');
      }
    });

    // Risk Limits Form Submit
    dom.limitsForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      // Server RiskLimits schema: max_drawdown_pct / max_daily_loss_pct.
      const payload = {
        max_position_size_pct: parseFloat(dom.limitMaxPos.value),
        max_drawdown_pct: parseFloat(dom.limitMaxDd.value),
        max_daily_loss_pct: parseFloat(dom.limitDailyLoss.value),
        default_stop_distance_pct: parseFloat(dom.limitStopDist.value),
      };
      const res = await apiFetch('/api/control/risk-limits', {
        method: 'PATCH',
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        showToast(state.lang === 'ar' ? 'تم حفظ حدود المخاطر بعد التحقق' : 'Risk limits validated and saved', 'success');
        await refreshAuthoritativeOverview();
      } else {
        showToast(await formatApiError(res, state.lang === 'ar' ? 'تعذر حفظ حدود المخاطر' : 'Failed to save risk limits'), 'error');
      }
    });

    // Live Unlock Form Submit
    dom.liveUnlockForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const phrase = dom.livePhraseInput.value.trim();
      const secondCheck = dom.liveStepTwoCheck.checked;
      const res = await apiFetch('/api/control/live-unlock', {
        method: 'POST',
        body: JSON.stringify({ confirmation_phrase: phrase, second_confirmation: secondCheck }),
      });
      if (res.ok) {
        showToast('Live profile unlocked successfully!', 'success');
        dom.liveGateEnvStatus.textContent = 'UNLOCKED';
        dom.liveGateEnvStatus.className = 'badge badge-success font-mono';
      } else {
        showToast(await formatApiError(res, state.lang === 'ar' ? 'تم رفض فتح التداول الحي' : 'Live unlock rejected'), 'error');
      }
    });

    // Theme form submit
    if (dom.themeForm) {
      dom.themeForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const payload = {
          branding: {
            platform_name: dom.themePlatformName.value,
            platform_subtitle: dom.themePlatformSubtitle.value,
            logo_url: dom.themeLogoUrl.value,
          },
          theme: {
            primary_color: dom.themePrimaryColor.value,
            accent_color: dom.themeAccentColor.value,
            bg_primary: dom.themeBgPrimary.value,
          },
        };
        const res = await apiFetch('/api/settings/theme', {
          method: 'PUT',
          body: JSON.stringify(payload),
        });
        if (res.ok) {
          showToast('Theme saved and applied', 'success');
          await loadAndApplyTheme();
        }
      });
    }

    // Theme reset button
    if (dom.btnResetTheme) {
      dom.btnResetTheme.addEventListener('click', async () => {
        const res = await apiFetch('/api/settings/theme/reset', { method: 'POST' });
        if (res.ok) {
          showToast('Theme reset to defaults', 'info');
          await loadAndApplyTheme();
        }
      });
    }

    // Audit refresh & filter
    if (dom.btnRefreshAudit) dom.btnRefreshAudit.addEventListener('click', loadAuditLogs);
    if (dom.auditActionFilter) dom.auditActionFilter.addEventListener('change', loadAuditLogs);

    // Reports refresh
    if (dom.btnRefreshReports) dom.btnRefreshReports.addEventListener('click', loadReports);

    window.addEventListener('resize', () => {
      renderEquityChart();
      if (state.lastPerformanceReport) renderPerformanceReport(state.lastPerformanceReport);
    });
  }

  // ── Theme & Branding ─────────────────────────────────────────────────────
  async function loadAndApplyTheme() {
    try {
      const res = await apiFetch('/api/settings/theme', { silent: true });
      if (!res.ok) return;
      const data = await res.json();
      const root = document.documentElement;
      const theme = data.theme || {};
      const branding = data.branding || {};
      // Apply theme CSS custom properties
      if (theme.primary_color) root.style.setProperty('--accent-blue', theme.primary_color);
      if (theme.accent_color) root.style.setProperty('--accent-cyan', theme.accent_color);
      if (theme.success_color) root.style.setProperty('--success', theme.success_color);
      if (theme.warning_color) root.style.setProperty('--warning', theme.warning_color);
      if (theme.danger_color) root.style.setProperty('--danger', theme.danger_color);
      if (theme.bg_primary) root.style.setProperty('--bg-primary', theme.bg_primary);
      if (theme.bg_secondary) root.style.setProperty('--bg-secondary', theme.bg_secondary);
      if (theme.text_primary) root.style.setProperty('--text-primary', theme.text_primary);
      if (theme.text_secondary) root.style.setProperty('--text-secondary', theme.text_secondary);
      // Apply branding
      if (branding.platform_name) {
        const brandTitle = document.querySelector('.brand-title');
        if (brandTitle) brandTitle.textContent = branding.platform_name;
        document.title = branding.platform_name + ' — ' + (branding.platform_subtitle || 'Management Console');
      }
      if (branding.platform_subtitle) {
        const brandSub = document.querySelector('.brand-sub');
        if (brandSub) brandSub.textContent = branding.platform_subtitle;
      }
      if (branding.logo_url) {
        const logoImg = document.createElement('img');
        logoImg.src = branding.logo_url;
        logoImg.alt = branding.platform_name || 'Logo';
        logoImg.style.cssText = 'height:22px;width:22px;object-fit:contain;border-radius:4px;';
        const logoBadge = document.querySelector('.logo-badge');
        if (logoBadge) { logoBadge.innerHTML = ''; logoBadge.appendChild(logoImg); }
      }
    } catch (_e) { /* Settings API unavailable — use defaults */ }
  }

  // ── Application Initialization ────────────────────────────────────────────
  async function init() {
    applyLanguage(state.lang);
    initTabs();
    initEventListeners();
    await checkAuth();
    await loadAndApplyTheme();
    initSSE();
  }

  document.addEventListener('DOMContentLoaded', init);
})();
