# خطة التنفيذ الشاملة — AI Quant Trading Platform

> **المسمى الوظيفي:** مدير فريق تطوير المشروع  
> **المشروع:** `python-trading-robot-master` → **AI Quant Trading Platform**  
> **إعداد:** 2026-08-19  
> **المرجع:** [AI_Quant_Trading_Platform_Master_Development_Prompt.md](file:///e:/pyhton/python-trading-robot/python-trading-robot-master/python-trading-robot-master/reports/AI_Quant_Trading_Platform_Master_Development_Prompt.md) + [report-GPT+1.md](file:///e:/pyhton/python-trading-robot/python-trading-robot-master/python-trading-robot-master/reports/report-GPT+1.md)

---

## 📋 ملخص تنفيذي

المشروع الحالي هو إطار تداول تقني (**Technical Analysis Framework**)، والهدف تحويله إلى:

> **AI-assisted Quantitative Trading Platform**

يقاس النجاح لا بعدد الميزات، بل بـ: جودة البيانات · صحة الـBacktesting · غياب Data Leakage · Out-of-Sample Performance · إدارة المخاطر · موثوقية التنفيذ.

---

## 📊 تقييم الحالة الراهنة

| الجانب | التقييم الحالي | الهدف |
|---|---|---|
| هندسة البرمجيات | 8/10 ✅ | الحفاظ عليها |
| Broker Abstraction | 8.5/10 ✅ | إصلاح ثغرات الـOrder Model |
| Testing | 7/10 🟡 | توسيع التغطية + Research Tests |
| Backtesting | 4/10 🔴 | إعادة بناء Event-driven |
| Risk Management | 4/10 🔴 | بناء Risk Engine مستقل |
| Strategy Engine | 3/10 🔴 | بناء Multi-Strategy Architecture |
| Machine Learning / AI | 2/10 🔴 | بناء ML Pipeline كامل |
| Production Readiness | 3.5/10 🔴 | Kill Switch + Monitoring + Audit |

> [!IMPORTANT]
> القاعدة الذهبية: **ممنوع الانتقال إلى Live Trading بأموال حقيقية لمجرد أن الـBacktest أعطى أرباحًا.**

---

## 🏗️ المعمارية المستهدفة (هيكل المجلدات)

```
python-trading-platform/
│
├── data/
│   ├── market/          # OHLCV, Quotes, Order Book
│   ├── fundamentals/    # Earnings, Financials
│   ├── options/         # Options Data
│   ├── macro/           # Macro Data
│   ├── news/            # News Feed
│   ├── sentiment/       # Sentiment Data
│   └── processed/       # Processed/Clean Data
│
├── research/
│   ├── datasets/        # Dataset Versioning
│   ├── features/        # Feature Store
│   ├── experiments/     # Experiment Tracking
│   └── validation/      # Walk-Forward / OOS Results
│
├── models/
│   ├── classifiers/     # XGBoost, LightGBM, CatBoost
│   ├── regressors/      # Return Models
│   ├── regime/          # Market Regime Detection
│   └── ensemble/        # Ensemble Logic
│
├── strategies/
│   ├── trend/
│   ├── mean_reversion/
│   ├── momentum/
│   ├── volatility/
│   └── ai/
│
├── portfolio/
│   ├── optimizer/
│   ├── allocator/
│   └── exposure/
│
├── risk/
│   ├── manager.py
│   ├── position_sizing.py
│   ├── exposure.py
│   ├── limits.py
│   ├── drawdown.py
│   ├── portfolio_risk.py
│   └── kill_switch.py
│
├── execution/
│   ├── engine.py
│   ├── order_manager.py
│   ├── execution_policy.py
│   ├── slippage.py
│   ├── reconciliation.py
│   └── idempotency.py
│
├── brokers/             # (موجود — يحتاج إصلاح)
│
├── backtesting/
│   ├── event_engine.py  # Event-driven Engine
│   ├── walk_forward.py
│   ├── monte_carlo.py
│   └── cost_model.py    # ExecutionCostModel
│
├── ai/
│   ├── sentiment/
│   ├── news/
│   ├── regime/
│   └── llm/             # Intelligence Layer (ليس Execution Brain)
│
├── monitoring/
│   ├── dashboard.py
│   ├── drift_detector.py
│   ├── alerts.py
│   └── audit_trail.py
│
└── tests/
    ├── unit/
    ├── integration/
    ├── e2e/
    └── failure/
```

---

## 🔄 تدفق القرار (Data Flow)

```
Market Data (OHLCV + News + Macro + Sentiment)
         ↓
   Data Quality Engine
         ↓
   Feature Engineering
         ↓
   ML Models (XGBoost / LightGBM / Regime)
         ↓
   Signal Engine → Signal(symbol, action, probability, confidence)
         ↓
   Risk Engine (Pre-trade checks)
         ↓
   Position Sizing
         ↓
   Execution Engine → Order (with client_order_id)
         ↓
   Broker Gateway
         ↓
   Order Lifecycle (NEW→SUBMITTED→FILLED / REJECTED / UNKNOWN)
         ↓
   Portfolio Reconciliation
         ↓
   Monitoring + Audit Trail
```

> [!WARNING]
> **الـLLM لا يولّد أوامر مباشرة.** الـAI يُنتج Probability/Forecast يمر عبر Signal Engine ثم Risk Engine ثم Execution Engine.

---

## 🚀 خطة الـSprints (ترتيب الأولويات)

---

### Sprint Group 0 — P0: Production Safety (الأولوية: Critical)

> **المدة المقدرة:** 2–3 أسابيع

هذه المرحلة قبل أي إضافة AI أو Features جديدة.

#### 0.1 — Unified Order Model

إنشاء نموذج أمر موحد واحد لكل الـBroker Adapters:

```python
Order(
    symbol,
    side,                # BUY / SELL
    quantity,
    order_type,          # MARKET / LIMIT / STOP
    limit_price,
    stop_price,
    time_in_force,
    strategy_id,
    signal_id,
    client_order_id,     # Idempotency Key
)
```

**المشكلة الحالية:** كل Broker Adapter يقرأ الـsymbol بطريقة مختلفة. يجب Canonical Order Schema واحد.

#### 0.2 — إصلاح Alpaca Order Mapping

- **الخلل:** `AlpacaBroker.place_order()` يقرأ `order.get("symbol", "")` بينما الـsymbol داخل `orderLegCollection[0].instrument.symbol`
- **الإصلاح:** استخراج موحد عبر Order Model

#### 0.3 — إصلاح IBKR Order State Bug (خطير)

- **الخلل:** إذا لم يجد الـorder في `openTrades()` يُرجع `status = "FILLED"` — هذا خطأ إنتاجي حرج.
- **الإصلاح:** إرجاع `status = "UNKNOWN"` ثم Reconciliation مع الـBroker

#### 0.4 — Order Lifecycle الكامل

```
NEW → SUBMITTED → ACKNOWLEDGED → PARTIALLY_FILLED → FILLED
                                              ↓
                              CANCEL_PENDING → CANCELLED
                              REJECTED
                              EXPIRED
                              UNKNOWN  ← (يستلزم Reconciliation)
```

#### 0.5 — Idempotency

كل Order يمتلك `client_order_id` لمنع التكرار عند:
API Retry · Network Timeout · Process Restart · Broker Response Timeout

#### 0.6 — Retry Policy الصحيحة

| نوع الخطأ | الإجراء |
|---|---|
| Timeout / 429 / 5xx / Network Failure | ✅ Retry |
| Order Rejected / Invalid Order / Insufficient Buying Power | ❌ لا Retry |

#### 0.7 — Time Handling

استخدام `timezone-aware datetime` في كل المشروع، توحيد داخلي على **UTC**.

#### 0.8 — Kill Switch

```python
# يوقف جميع الأوامر الجديدة عند:
- Daily Loss Limit breached
- Maximum Drawdown breached
- Data feed stale
- Broker disconnected
- Unexpected position mismatch
- Repeated order failures
- System health failure
```

#### 0.9 — Regression Tests

اختبارات لكل السيناريوهات السابقة قبل الانتقال.

---

### Sprint Group 1 — P1: Data Platform (الأولوية: Critical / High)

> **المدة المقدرة:** 3–4 أسابيع

#### 1.1 — Data Layer مستقلة عن Broker Layer

```python
class MarketDataProvider:
    def get_historical(symbol, start, end, timeframe) -> DataFrame
    def get_realtime(symbol) -> Stream
    def get_options(symbol) -> OptionsChain
    def get_fundamentals(symbol) -> Fundamentals
```

#### 1.2 — Data Quality Engine

قبل دخول أي بيانات للنظام، التحقق من:

| الفحص | التفصيل |
|---|---|
| Missing Candles | اكتشاف الفجوات الزمنية |
| Duplicated Candles | إزالة التكرار |
| Wrong Timestamps | التحقق من الترتيب الزمني |
| Negative / Impossible Prices | OHLC Consistency |
| Zero Volume Anomalies | فحص أيام التداول الصفرية |
| Corporate Actions | Split / Dividend Adjustments |
| Timezone Inconsistencies | توحيد UTC |

كل Dataset يمتلك: `dataset_id · source · retrieved_at · time_range · symbol_universe · data_version · adjustment_policy`

#### 1.3 — Storage المناسب

| النوع | Storage |
|---|---|
| Raw Historical (صغير) | Parquet Files |
| Research Data | DuckDB |
| Time-series Production | TimescaleDB / PostgreSQL |
| Features | Parquet + Feature Store |

#### 1.4 — Dataset Versioning

Immutable datasets مع Version Tags لضمان Reproducibility.

---

### Sprint Group 2 — P1: إعادة بناء Backtesting Engine (الأولوية: Critical)

> **المدة المقدرة:** 4–5 أسابيع

هذه من **أهم مراحل المشروع**.

#### 2.1 — Event-driven Architecture

```
MarketEvent → Strategy → Signal → Risk → Order → ExecutionSimulator → Fill → PortfolioUpdate
```

كل مكون مستقل تمامًا.

#### 2.2 — ExecutionCostModel (بدلًا من fixed slippage فقط)

```
Bid/Ask Spread
+ Slippage (Volatility-dependent)
+ Market Impact
+ Volume Participation Limit
+ Partial Fills
+ Latency Simulation
+ Order Queue
+ Gap Risk
+ Trading Session Boundaries
```

**المشكلة الحالية:** `fill_price = price * (1 + slippage_pct)` — نسبة ثابتة فقط.

#### 2.3 — Multi-Asset Per-Symbol Signals

الاستراتيجية تُصدر إشارات مستقلة:
```
AAPL → BUY
MSFT → HOLD
NVDA → SELL
TSLA → NO TRADE
```

لا: `BUY → اشترِ كل شيء`

#### 2.4 — Walk-Forward Validation (أولوية رقم 1 قبل AI)

```
Train 2020-2022 | Validate 2023 | Test 2024
Train 2021-2023 | Validate 2024 | Test 2025
...
```

نتائج الـOut-of-Sample منفصلة تمامًا عن Training.

#### 2.5 — Advanced Validation Suite

```
Purged K-Fold Cross Validation
+ Embargo (لمنع Leakage الزمني)
+ Walk-Forward
+ Monte Carlo Simulation
+ Parameter Stability Analysis
+ Sensitivity Analysis
+ Stress Testing
+ Regime-specific Evaluation
```

#### 2.6 — Backtesting Metrics الموسعة

| الموجود | المضاف |
|---|---|
| Return, Sharpe, Sortino, Drawdown, Win Rate, Profit Factor | Calmar, Ulcer Index, Annualized Volatility, Average Trade, Expectancy, Turnover, Exposure (Long/Short/Gross/Net), Max Consecutive Losses, Average Holding Period, VaR, CVaR, Tail Loss |

#### 2.7 — Data Leakage Tests

اختبارات آلية تكتشف:
- Look-ahead Bias
- Target Leakage
- Future Information Leakage
- Improper Normalization

**قاعدة:** كل Feature يجب أن يُجيب على: *هل كانت هذه المعلومة متاحة فعليًا في لحظة اتخاذ القرار؟*

---

### Sprint Group 3 — P2: Risk Engine (الأولوية: Critical)

> **المدة المقدرة:** 3–4 أسابيع

#### 3.1 — RiskManager المستقل

```
risk/
├── manager.py
├── position_sizing.py
├── exposure.py
├── limits.py
├── drawdown.py
├── portfolio_risk.py
└── kill_switch.py
```

#### 3.2 — Pre-trade Risk Checks

قبل كل أمر، التحقق من:
```
max_position_size          ✓
max_daily_loss             ✓
max_drawdown               ✓
max_portfolio_exposure     ✓
max_symbol_exposure        ✓
max_sector_exposure        ✓
max_leverage               ✓
max_open_positions         ✓
max_order_value            ✓
max_volume_participation   ✓
liquidity_limit            ✓
volatility_limit           ✓
correlation_limit          ✓
```

إذا فشل أي شرط → **DO NOT TRADE**

#### 3.3 — Position Sizing الذكي

```python
position_size = RiskEngine.size(
    signal_confidence,    # من ML Model
    volatility,           # Historical / Realized
    account_size,
    portfolio_exposure,   # الـExposure الحالي
    correlation,          # مع المحفظة
    max_risk_per_trade,
    drawdown_state,       # هل نحن في drawdown؟
)
```

**الـPosition Size = output من Risk Engine، وليس من Strategy Engine.**

#### 3.4 — Portfolio-Level Risk

```
Gross Exposure / Net Exposure
Sector Exposure / Factor Exposure
Correlation Matrix
Concentration Risk
Portfolio Volatility
Portfolio Drawdown
```

#### 3.5 — Runtime Protection

```
API disconnected            → PAUSE
Price feed stale            → PAUSE
Duplicate order detected    → REJECT
Abnormal volatility         → ALERT + REDUCE
Loss threshold breached     → KILL SWITCH
Model drift detected        → ALERT + REVIEW
```

---

### Sprint Group 4 — P3: Strategy Engine (الأولوية: High)

> **المدة المقدرة:** 3–4 أسابيع

#### 4.1 — BaseStrategy Abstraction

```python
class BaseStrategy:
    def generate_signals(market_data, features) -> Dict[str, Signal]
    def get_strategy_id(self) -> str
    def get_parameters(self) -> dict
```

#### 4.2 — أنواع الاستراتيجيات المدعومة

```
Trend Following
Momentum
Mean Reversion
Breakout
Volatility
Statistical Arbitrage
AI-based Strategies
```

#### 4.3 — Unified Signal Model

```python
Signal(
    symbol,
    action,       # BUY / SELL / HOLD / NO_TRADE
    probability,  # من ML Model
    confidence,   # 0.0 → 1.0
    timestamp,
    strategy_id,
    model_id,
    reason,       # للـAudit Trail
)
```

#### 4.4 — Regime Detection (مكوّن أساسي)

```python
class RegimeDetector:
    def detect(market_data) -> Regime

# Regimes:
BULL       → Trend Following
BEAR       → Defensive / Short
SIDEWAYS   → Mean Reversion
HIGH_VOL   → Reduce Position Size
LOW_VOL    → Increase Selectivity
CRISIS     → No Trade / Hedge
```

---

### Sprint Group 5 — P4: AI/ML Layer (الأولوية: High)

> **المدة المقدرة:** 5–6 أسابيع

#### 5.1 — Feature Engineering Pipeline

| مجموعة | Features |
|---|---|
| Price | Returns, Log Returns, Momentum, ATR, Rolling High/Low, Gap, Range |
| Technical | RSI, EMA, SMA, ADX, VWAP, OBV, CCI, Bollinger, Ichimoku, MACD |
| Volume | Volume Change, Relative Volume, Volume Imbalance, VWAP Deviation |
| Volatility | Historical Volatility, ATR, Realized Volatility, Volatility Percentile |
| Market Context | Index Trend, Market Breadth, Sector Performance, VIX Context, Correlation |

#### 5.2 — ML Models (بالترتيب)

```
المرحلة 1: Technical + Price Features (Baseline)
المرحلة 2: XGBoost / LightGBM / CatBoost
المرحلة 3: Regime Detection Model
المرحلة 4: Ensemble Models
المرحلة 5: NLP / Sentiment / News
المرحلة 6: Deep Learning / Temporal Models (LSTM, Transformer)
المرحلة 7: LLM Intelligence Layer
المرحلة 8: Reinforcement Learning (فقط بعد نضج كل ما سبق)
```

> [!CAUTION]
> لا نبدأ بـDeep Learning / RL قبل ضمان جودة البيانات وصحة الـBacktesting والـRisk Engine.

#### 5.3 — AI Targets (متعددة)

| النوع | Target |
|---|---|
| Classification | P(Return > threshold) |
| Regression | Expected Return |
| Volatility | Expected Volatility |
| Regime | Bull / Bear / Sideways / High-Vol / Crisis |

#### 5.4 — Ensemble Model

```
XGBoost Probability
+ LightGBM Probability
+ Technical Strategy Signal
+ Regime Model Output
        ↓
   Ensemble Aggregator
        ↓
Final Signal(probability, confidence, expected_return, expected_risk)
```

#### 5.5 — Model Registry

```yaml
model_id:          "trend_xgb_v3"
version:           "3.2.1"
training_period:   "2020-01-01 to 2023-12-31"
features_version:  "v2.1"
dataset_version:   "ds_20240101"
hyperparameters:   {...}
metrics:           {sharpe: 1.8, oos_return: 12.3}
validation:        {walk_forward: passed, monte_carlo: passed}
approval_status:   "approved"
deployment_status: "production"
```

**لا يُسمح بتشغيل نموذج في الإنتاج بدون Version واضح.**

#### 5.6 — Model Monitoring

```
Prediction Drift    → ALERT
Feature Drift       → ALERT + REVIEW
Data Drift          → ALERT
Confidence Drift    → REDUCE EXPOSURE
Performance Drift   → SUSPEND MODEL
Calibration Error   → RETRAIN
```

---

### Sprint Group 6 — P5: LLM / Intelligence Layer (الأولوية: Medium)

> **المدة المقدرة:** 3–4 أسابيع

> [!IMPORTANT]
> الـLLM **ليس** Execution Brain. هو Intelligence Layer فقط.

#### 6.1 — استخدامات LLM المقبولة

```
News Classification & Summarization
Sentiment Extraction
Event Detection & Classification
Market Commentary
Trade Explanation (لماذا اتخذ النظام هذا القرار؟)
Post-trade Analysis
Anomaly Explanation
Research Assistant
Risk Context
```

#### 6.2 — LLM Output → Feature Engine

```
LLM Output:
  News Sentiment = -0.72
  Event = Earnings Miss
  Importance = High
  Affected Symbol = XYZ
  Confidence = 0.91
        ↓
Feature Engine → Signal Engine → Risk Engine → Order
```

**الـLLM لا يُرسل Order مباشرة إلى Broker.**

---

### Sprint Group 7 — P6: Monitoring & Observability (الأولوية: High)

> **المدة المقدرة:** 2–3 أسابيع

#### 7.1 — Trading Dashboard

```
Account Equity (Real-time)
Daily P&L
Drawdown (Current / Max)
Open Positions
Portfolio Exposure (Gross / Net)
Orders (Pending / Filled / Rejected)
Fills + Latency
Model Confidence (Per Symbol)
Current Market Regime
Strategy Performance
Broker Health Status
Data Feed Health
```

#### 7.2 — Audit Trail (كل قرار قابل للتتبع)

```yaml
timestamp:       "2026-08-19T10:23:45Z"
symbol:          "AAPL"
market_state:    {regime: "BULL", vix: 18.2}
features:        {rsi: 45.2, macd_hist: 0.12, ...}
model_version:   "trend_xgb_v3"
signal:          "BUY"
probability:     0.78
confidence:      0.82
risk_decision:   "APPROVED"
position_size:   1.8%
order_id:        "ord_20260819_001"
broker_response: "SUBMITTED"
fill_price:      182.45
result:          "FILLED"
```

---

### Sprint Group 8 — P7: Deployment Pipeline (الأولوية: High)

> **المدة المقدرة:** 4–6 أسابيع

#### 8.1 — مسار النشر الإلزامي

```
Backtest (Event-driven)
        ↓
Out-of-Sample Validation (Walk-Forward + Monte Carlo)
        ↓
Paper Trading (≥ 3 أشهر)
        ↓
Shadow Mode (النظام يقرر لكن لا يُرسل)
        ↓
Very Small Capital ($100-$500)
        ↓
Controlled Live ($1,000)
        ↓
Gradual Scaling (بحذر + مراقبة مستمرة)
```

#### 8.2 — Shadow Mode

النظام يُصدر قرار BUY/SELL → يسجّله → لا يُرسله → يقارن بما حدث فعليًا في السوق.

#### 8.3 — Real-time Architecture

```
WebSocket Streaming (ليس Polling فقط)
+ Heartbeat
+ Auto-reconnect with backoff
+ Stale data detection
+ Feed health monitoring
```

---

## 🧪 استراتيجية الاختبار

| النوع | الأهداف |
|---|---|
| **Unit Tests** | Indicator, Feature, Signal, Risk Rule, Position Sizing, Order Normalization, Broker Adapter |
| **Integration Tests** | Strategy → Risk → Execution → Paper Broker |
| **End-to-End Tests** | Market Data → Strategy → Risk → Order → Fill → Portfolio |
| **Failure Tests** | Broker Outage, Network Timeout, Duplicate Response, Stale Data, Bad Market Data, Partial Fill, Rejected Order, Unknown Order State, Process Restart |
| **Research Validation** | Walk-Forward, OOS, Monte Carlo, Leakage Detection |

> [!NOTE]
> **91 test passed ≠ strategy profitable**  
> الاختبارات الحالية تثبت أن الـCode يعمل، لا أن الاستراتيجية تُولّد Alpha. نحتاج **Research Validation Suite** منفصلة.

---

## 🔒 الأمان والإنتاج

#### Security Rules

```
❌ ممنوع: API Keys / Secrets في Git أو Source Code أو Logs
✅ مطلوب: Environment Variables + Secret Manager + Encrypted Storage
```

#### CI/CD Pipeline يفشل عند:

```
Tests failing
Type errors (mypy)
Lint errors (Ruff)
Security vulnerabilities
Coverage regression
Secret scanning failures
```

#### Definition of Done

Feature = مكتملة فقط عند وجود:
```
Implementation + Unit Tests + Integration Tests + Error Handling
+ Logging + Documentation + Metrics + Security Review
```

---

## ⛔ الممنوعات (قواعد لا استثناء فيها)

| الممنوع | البديل |
|---|---|
| إضافة مؤشرات بدون Hypothesis | تحديد Hypothesis قبل التطوير |
| AI لأجل التسويق فقط | AI لأجل تحسين جودة القرار |
| LLM يُعطي BUY/SELL مباشرة | LLM → Sentiment/Event → Feature Engine |
| الاعتماد على Backtest واحد | Walk-Forward + Monte Carlo + OOS |
| اختيار Hyperparameters من Test Set | Nested CV + Hold-out Set منفصل |
| استخدام بيانات مستقبلية | Look-ahead Bias Tests إلزامية |
| Live Trading قبل Paper + Shadow | اتباع مسار النشر الإلزامي |
| Win Rate كمقياس رئيسي | Risk-adjusted Return + Robustness |
| توسيع رأس المال بعد أول نجاح | مراقبة ≥ 6 أشهر قبل أي توسيع |

---

## 📋 معيار قبول الاستراتيجية

لا تُقبل Strategy جديدة بمجرد `Total Return > 0`. يجب:

```
OOS Return (Out-of-Sample)
+ Sharpe Ratio (> 1.0 مقبول، > 1.5 جيد)
+ Sortino Ratio
+ Calmar Ratio
+ Max Drawdown (< 20% مقبول)
+ Profit Factor (> 1.5)
+ Expectancy (موجبة)
+ Turnover (معقول)
+ Transaction Costs (مُدرجة في الحساب)
+ Stability (مستقر عبر Sub-periods)
+ Regime Robustness (يعمل في Bull + Bear + Sideways)
+ Parameter Robustness (لا يعتمد على Hyperparameter ضيق)
+ Monte Carlo Drawdown (Worst case مقبول)
```

---

## 📝 تقرير ما بعد كل Phase

عند إنهاء كل Sprint Group، الفريق يُقدم:

1. ما الذي تم تنفيذه؟
2. ما الملفات التي تغيرت؟
3. ما الافتراضات التي تم اتخاذها؟
4. ما الاختبارات التي أُضيفت؟
5. ما الاختبارات التي نجحت؟
6. ما الذي لا يزال خطرًا؟
7. ما تأثير الأداء؟
8. ما الآثار الأمنية؟
9. ما خطوات الـMigration المطلوبة؟
10. ما المرحلة التالية؟

---

## 🎯 ملخص الجدول الزمني التقديري

| Sprint Group | المحتوى | الأولوية | المدة التقديرية |
|---|---|---|---|
| **SG-0** | Production Safety + Order Model + Kill Switch | P0 Critical | 2–3 أسابيع |
| **SG-1** | Data Platform + Data Quality Engine | P1 Critical | 3–4 أسابيع |
| **SG-2** | Event-driven Backtesting + Walk-Forward + OOS | P1 Critical | 4–5 أسابيع |
| **SG-3** | Risk Engine + Position Sizing + Portfolio Risk | P2 Critical | 3–4 أسابيع |
| **SG-4** | Strategy Engine + Regime Detection | P3 High | 3–4 أسابيع |
| **SG-5** | AI/ML Pipeline + Model Registry + Monitoring | P4 High | 5–6 أسابيع |
| **SG-6** | LLM Intelligence Layer + Sentiment + News | P5 Medium | 3–4 أسابيع |
| **SG-7** | Monitoring + Dashboard + Audit Trail | P6 High | 2–3 أسابيع |
| **SG-8** | Paper → Shadow → Small Capital → Controlled Live | P7 High | 4–6 أسابيع |
| **إجمالي** | | | **~29–39 أسبوعًا** |

---

## 🏆 المعيار النهائي للمشروع

النظام الناجح يمتلك هذه الصفات:

```
Reliable        — يعمل بشكل موثوق في حالات الفشل
Observable      — نرى كل ما يحدث في الوقت الفعلي
Testable        — كل مكون قابل للاختبار المستقل
Risk-controlled — Risk Engine مستقل يحمي رأس المال
Broker-agnostic — يعمل مع أي Broker عبر Abstraction Layer
Data-driven     — كل قرار مبني على بيانات عالية الجودة
Model-aware     — نماذج ذات Version + Registry + Monitoring
AI-assisted     — AI كطبقة ذكاء، ليس كـExecution Brain
Reproducible    — كل نتيجة قابلة للإعادة والتحقق
Auditable       — كل قرار له سجل كامل وقابل للتتبع
Scalable        — يتمدد بأمان مع زيادة رأس المال والأصول
```

> **الهدف النهائي:**  
> بناء نظام يُثبت وجود **Edge** بصورة منهجية، ثم اختبار استمرار هذا الـEdge خارج العينة وتحت تكاليف التنفيذ الحقيقية، قبل تعريض أي رأس مال للخطر.

---

*إعداد: مدير فريق تطوير المشروع · 2026-08-19*
