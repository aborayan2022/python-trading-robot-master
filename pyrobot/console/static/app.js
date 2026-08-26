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
      btn_confirm: "تأكيد وتنفيذ"
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
      btn_confirm: "Confirm & Execute"
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
    limitsForm: document.getElementById('limits-form'),
    limitMaxPos: document.getElementById('limit-max-pos'),
    limitMaxDd: document.getElementById('limit-max-dd'),
    limitDailyLoss: document.getElementById('limit-daily-loss'),
    limitStopDist: document.getElementById('limit-stop-dist'),
    liveUnlockForm: document.getElementById('live-unlock-form'),
    livePhraseInput: document.getElementById('live-phrase-input'),
    liveStepTwoCheck: document.getElementById('live-step-two-check'),
    liveGateEnvStatus: document.getElementById('live-gate-env-status'),
    
    // Audit
    auditTbody: document.getElementById('audit-tbody'),
    auditActionFilter: document.getElementById('audit-action-filter'),
    btnRefreshAudit: document.getElementById('btn-refresh-audit'),
    
    // Modals
    modalBackdrop: document.getElementById('modal-backdrop'),
    loginModal: document.getElementById('login-modal'),
    loginForm: document.getElementById('login-form'),
    loginTokenInput: document.getElementById('login-token-input'),
    loginModalClose: document.getElementById('login-modal-close'),
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
  async function apiFetch(endpoint, options = {}) {
    const defaultHeaders = {
      'Content-Type': 'application/json',
    };
    try {
      const res = await fetch(endpoint, {
        ...options,
        headers: { ...defaultHeaders, ...(options.headers || {}) },
      });
      if (res.status === 401) {
        openLoginModal();
      }
      return res;
    } catch (err) {
      showToast(`Network error: ${err.message}`, 'error');
      throw err;
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
        if (tab === 'control') loadRiskLimits();
        if (tab === 'overview') renderEquityChart();
      });
    });
  }

  // ── Authentication & Roles ────────────────────────────────────────────────
  async function checkAuth() {
    try {
      const res = await apiFetch('/api/auth/me');
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

    // Refresh child tables
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
      const res = await apiFetch('/api/positions');
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
    } catch {}
  }

  async function loadOrders() {
    try {
      const res = await apiFetch('/api/orders');
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
    } catch {}
  }

  async function loadSignals() {
    try {
      const res = await apiFetch('/api/signals?limit=15');
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
    } catch {}
  }

  // ── Audit Logs ────────────────────────────────────────────────────────────
  async function loadAuditLogs() {
    try {
      const filter = dom.auditActionFilter ? dom.auditActionFilter.value : '';
      const url = filter ? `/api/audit?action=${encodeURIComponent(filter)}&limit=50` : '/api/audit?limit=50';
      const res = await apiFetch(url);
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
    } catch {}
  }

  // ── Risk Limits & Configuration ───────────────────────────────────────────
  async function loadRiskLimits() {
    try {
      const res = await apiFetch('/api/control/risk-limits');
      if (res.ok) {
        const limits = await res.json();
        dom.limitMaxPos.value = limits.max_position_size_pct || 0.10;
        dom.limitMaxDd.value = limits.max_portfolio_drawdown_pct || 0.15;
        dom.limitDailyLoss.value = limits.daily_loss_limit_pct || 0.03;
        dom.limitStopDist.value = limits.default_stop_distance_pct || 0.02;
      }
    } catch {}
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
        showToast('Login successful', 'success');
        closeModals();
        await checkAuth();
      } else {
        showToast('Invalid access token', 'error');
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
      if (res.ok) showToast('Engine started', 'success');
    });

    dom.btnCtrlPause.addEventListener('click', async () => {
      const res = await apiFetch('/api/control/pause', { method: 'POST' });
      if (res.ok) showToast('Engine paused', 'warning');
    });

    dom.btnCtrlResume.addEventListener('click', async () => {
      const res = await apiFetch('/api/control/resume', { method: 'POST' });
      if (res.ok) showToast('Engine resumed', 'success');
    });

    dom.btnCtrlStop.addEventListener('click', () => {
      showConfirmDialog(
        state.lang === 'ar' ? 'إيقاف المحرك' : 'Stop Engine',
        state.lang === 'ar' ? 'هل أنت متأكد من إيقاف حلقة التداول رشيقة؟' : 'Are you sure you want to gracefully stop the trading loop?',
        async () => {
          const res = await apiFetch('/api/control/stop', { method: 'POST' });
          if (res.ok) showToast('Engine stopped gracefully', 'info');
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
          if (res.ok) showToast('Kill switch activated!', 'error');
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
          if (res.ok) showToast('Kill switch reset', 'success');
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
        initial_balance: parseFloat(dom.cfgBalance.value),
      };
      const res = await apiFetch('/api/control/config', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      if (res.ok) showToast('Configuration applied with graceful restart', 'success');
    });

    // Risk Limits Form Submit
    dom.limitsForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const payload = {
        max_position_size_pct: parseFloat(dom.limitMaxPos.value),
        max_portfolio_drawdown_pct: parseFloat(dom.limitMaxDd.value),
        daily_loss_limit_pct: parseFloat(dom.limitDailyLoss.value),
        default_stop_distance_pct: parseFloat(dom.limitStopDist.value),
      };
      const res = await apiFetch('/api/control/risk-limits', {
        method: 'PATCH',
        body: JSON.stringify(payload),
      });
      if (res.ok) showToast('Risk limits validated and saved', 'success');
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
        const err = await res.json();
        showToast(err.detail || 'Live unlock rejected', 'error');
      }
    });

    // Audit refresh & filter
    if (dom.btnRefreshAudit) dom.btnRefreshAudit.addEventListener('click', loadAuditLogs);
    if (dom.auditActionFilter) dom.auditActionFilter.addEventListener('change', loadAuditLogs);

    window.addEventListener('resize', renderEquityChart);
  }

  // ── Application Initialization ────────────────────────────────────────────
  async function init() {
    applyLanguage(state.lang);
    initTabs();
    initEventListeners();
    await checkAuth();
    initSSE();
  }

  document.addEventListener('DOMContentLoaded', init);
})();
