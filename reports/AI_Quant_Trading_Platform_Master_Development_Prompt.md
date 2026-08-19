# AI Quant Trading Platform — Master Development Prompt

## الوثيقة التنفيذية الموجهة لفريق التطوير

**Project:** `python-trading-robot-master`  
**Target:** تحويل المشروع من Trading Robot Framework إلى **Production-Grade AI Quantitative Trading Platform**  
**Current Version:** `v0.2.0`  
**Repository:** https://github.com/aborayan2022/python-trading-robot-master  
**Prepared:** 2026-08-19

---

# 1. تعليمات عامة للفريق

أنتم تعملون على مشروع تداول آلي حقيقي، وليس Demo أو مشروع تعليمي.

الهدف من هذا العمل هو **تطوير المشروع تدريجيًا إلى منصة Algorithmic/Quantitative Trading قابلة للاختبار الصارم والتشغيل الآمن**، مع إضافة طبقة AI بصورة صحيحة.

## قاعدة أساسية

لا تقيسوا نجاح المشروع بعدد الـfeatures أو عدد مؤشرات التحليل الفني.

نجاح المشروع يقاس بـ:

- جودة البيانات.
- صحة الـbacktesting.
- عدم وجود Look-ahead Bias أو Data Leakage.
- جودة Out-of-Sample performance.
- إدارة المخاطر.
- موثوقية تنفيذ الأوامر.
- إمكانية إيقاف النظام بأمان.
- قابلية تتبع كل قرار تداول.
- استقرار النظام تحت حالات الفشل.
- Robustness عبر فترات وأسواق مختلفة.

**ممنوع الانتقال إلى Live Trading بأموال حقيقية لمجرد أن الـbacktest أعطى أرباحًا.**

---

# 2. الحالة الحالية للمشروع

المشروع الحالي تم تحديثه بصورة جيدة من الناحية الهندسية.

بحسب التقرير الحالي، تم:

- إزالة الاعتماد التشغيلي على TD Ameritrade.
- إضافة Broker Abstraction Layer.
- دعم Paper Broker.
- دعم Alpaca / Schwab / IBKR.
- إصلاح أخطاء في مؤشرات Bollinger / Stochastic / CCI / KST.
- إصلاح منطق تنفيذ إشارات البيع.
- إضافة Backtesting Engine.
- إضافة Sharpe / Sortino / Maximum Drawdown / Win Rate / Profit Factor.
- إضافة Logging.
- تحديث Python packaging.
- إضافة pytest / mypy / Ruff.
- إضافة CI.
- وجود 91 اختبارًا ناجحًا.

هذه نقطة بداية جيدة، لكنها **لا تعني أن النظام أصبح AI Trading Platform أو أنه جاهز للتداول الحقيقي**.

المشروع حاليًا أقرب إلى:

> Broker-agnostic technical-analysis trading framework

ويجب نقله إلى:

> Quantitative + AI Trading Platform with production-grade risk and execution controls

---

# 3. الهدف النهائي

يجب أن تصبح المعمارية النهائية أقرب إلى:

```text
Market Data
     │
     ├── OHLCV
     ├── Quotes
     ├── Order Book / Liquidity
     ├── Options Data
     ├── Fundamentals
     ├── Macro Data
     └── News / Sentiment
            │
            ▼
      Data Engineering
            │
            ▼
      Feature Engineering
            │
            ▼
      Research / ML Models
            │
            ├── Direction Model
            ├── Return Model
            ├── Volatility Model
            ├── Regime Model
            └── Ensemble
            │
            ▼
       Signal Engine
            │
            ▼
        Risk Engine
            │
            ▼
     Portfolio / Allocation
            │
            ▼
      Execution Engine
            │
            ▼
       Broker Gateway
            │
            ▼
       Order / Fill
            │
            ▼
     Portfolio Reconciliation
            │
            ├── Monitoring
            ├── Alerts
            ├── Audit Logs
            ├── Model Monitoring
            └── Kill Switch
```

---

# 4. مبدأ معماري مهم

يجب فصل الطبقات التالية بشكل واضح:

```text
Data
Research
Features
Models
Strategies
Signals
Risk
Portfolio
Execution
Brokers
Monitoring
```

لا تسمحوا بوضع منطق الـstrategy داخل الـBroker.

ولا تضعوا منطق الـrisk داخل الـstrategy.

ولا تجعلوا الـLLM يتولى تنفيذ الأوامر مباشرة.

القرار النهائي يجب أن يمر عبر:

```text
Signal
→ Risk Validation
→ Position Sizing
→ Execution Validation
→ Order
```

---

# 5. Phase 0 — تدقيق وتصحيح Production-Critical Bugs

**الأولوية: Critical**

قبل إضافة أي AI أو Models، يجب مراجعة جميع مكونات النظام الحالي.

## المطلوب

### 5.1 Unified Order Model

إنشاء نموذج أمر موحد:

```python
Order(
    symbol,
    side,
    quantity,
    order_type,
    limit_price,
    stop_price,
    time_in_force,
    strategy_id,
    signal_id,
    client_order_id,
)
```

ممنوع أن تتعامل كل Broker Adapter مع شكل مختلف للأمر بدون طبقة normalization واضحة.

---

### 5.2 إصلاح Alpaca Order Mapping

يجب التأكد من أن الـsymbol يتم استخراجه بشكل صحيح من الـnormalized order representation.

لا تعتمدوا على:

```python
order.get("symbol")
```

إذا كان الـsymbol موجودًا داخل:

```python
orderLegCollection[].instrument.symbol
```

يجب وضع Canonical Order Schema واحد لكل broker.

---

### 5.3 إصلاح Order Lifecycle

يجب دعم الحالات:

```text
NEW
SUBMITTED
ACKNOWLEDGED
PARTIALLY_FILLED
FILLED
CANCEL_PENDING
CANCELLED
REJECTED
EXPIRED
UNKNOWN
```

ممنوع اعتبار:

```text
order not found
```

بأنه:

```text
FILLED
```

يجب وجود حالة:

```text
UNKNOWN
```

ثم إجراء reconciliation مع broker.

---

### 5.4 Idempotency

كل Order يجب أن يمتلك:

```text
client_order_id
```

لمنع duplicate orders عند:

- API retry.
- network timeout.
- process restart.
- broker response timeout.

---

### 5.5 Retry Policy

أضيفوا Retry فقط للأخطاء القابلة للإعادة.

مثلاً:

```text
Timeout
429
Temporary Network Failure
5xx
```

ولا تعيدوا تلقائيًا:

```text
Order Rejected
Invalid Order
Insufficient Buying Power
Invalid Symbol
```

---

### 5.6 Time Handling

استخدموا timezone-aware datetime في كل المشروع.

يجب توحيد الوقت داخليًا على UTC، مع تحويل الوقت لوقت السوق فقط عند الحاجة.

---

# 6. Phase 1 — Data Platform

**الأولوية: Critical / High**

لا يمكن بناء AI Trading جيد ببيانات ضعيفة.

## المطلوب

أنشئوا `Data Layer` مستقلة عن الـBroker Layer.

مثلاً:

```text
data/
├── market/
├── fundamentals/
├── options/
├── macro/
├── news/
├── sentiment/
└── processed/
```

## Data Sources

صمموا abstraction:

```python
MarketDataProvider
```

ثم adapters متعددة.

يجب الفصل بين:

```text
Historical Data
Real-time Data
Replay Data
Research Data
Live Data
```

---

# 7. Data Quality Engine

قبل دخول أي data إلى النظام:

تحققوا من:

- Missing candles.
- Duplicated candles.
- Wrong timestamps.
- Negative prices.
- Impossible OHLC relationships.
- Zero volume anomalies.
- Suspicious gaps.
- Corporate actions.
- Split adjustments.
- Dividend adjustments.
- Timezone inconsistencies.

كل dataset يجب أن يمتلك:

```text
dataset_id
source
retrieved_at
time_range
symbol universe
data version
adjustment policy
```

---

# 8. Storage

لا تجعلوا ملفات JSON هي المصدر الرئيسي لبيانات التداول الكبيرة.

استخدموا storage مناسبًا حسب الحجم، مثل:

```text
Parquet
DuckDB
PostgreSQL
TimescaleDB
```

مع إمكانية الاحتفاظ بـraw data وprocessed data بشكل منفصل.

---

# 9. Phase 2 — Research & Feature Engineering

**الأولوية: High**

أنشئوا:

```text
research/
├── datasets/
├── features/
├── experiments/
├── validation/
└── reports/
```

## Feature Groups

### Price Features

```text
Returns
Log Returns
Momentum
Volatility
ATR
Rolling High/Low
Gap
Range
```

### Technical Features

```text
RSI
EMA
SMA
ADX
VWAP
OBV
CCI
Bollinger
Ichimoku
MACD
```

### Volume Features

```text
Volume change
Relative volume
Volume imbalance
VWAP deviation
```

### Volatility Features

```text
Historical volatility
ATR
Realized volatility
Volatility percentile
```

### Market Context

```text
Index trend
Market breadth
Sector performance
VIX-like volatility context
Correlation
Risk-on / Risk-off
```

### News / Sentiment

لاحقًا:

```text
Sentiment score
Event type
Event importance
Entity
Expected direction
Confidence
```

---

# 10. Critical Rule — منع Data Leakage

كل Feature يجب أن يجيب بوضوح:

> هل كانت هذه المعلومة متاحة فعليًا في لحظة اتخاذ القرار؟

إذا كانت الإجابة لا:

**يمنع استخدامها.**

يجب إنشاء اختبارات آلية لاكتشاف:

```text
Look-ahead Bias
Target Leakage
Future information leakage
Improper normalization
```

---

# 11. Phase 3 — إعادة بناء Backtesting Engine

**الأولوية: Critical**

هذه واحدة من أهم مراحل المشروع.

الـBacktester الحالي جيد كبداية لكنه ليس كافيًا لتقييم استراتيجية Quant احترافية.

## المطلوب

تحويله إلى Event-driven Backtesting Engine.

المعمارية:

```text
Market Event
     ↓
Strategy
     ↓
Signal
     ↓
Risk
     ↓
Order
     ↓
Execution Simulator
     ↓
Fill
     ↓
Portfolio Update
```

---

# 12. Execution Simulation

يجب دعم:

```text
Bid / Ask spread
Slippage
Market impact
Partial fills
Liquidity limits
Latency
Order queue approximation
Volume participation
Gap risk
Trading session
```

لا تعتمدوا فقط على:

```python
price * (1 ± slippage_pct)
```

كـexecution model وحيد.

يجب أن يكون هناك `ExecutionCostModel`.

---

# 13. Backtesting Metrics

إلى جانب:

```text
Return
Sharpe
Sortino
Drawdown
Win Rate
Profit Factor
```

أضيفوا:

```text
Calmar Ratio
Ulcer Index
Annualized Volatility
Average Trade
Expectancy
Turnover
Exposure
Long Exposure
Short Exposure
Gross Exposure
Net Exposure
Maximum Consecutive Losses
Average Holding Period
Tail Loss
VaR
CVaR
```

---

# 14. Walk-Forward Validation

يجب منع:

```text
Train on everything
→ Backtest on everything
```

بدلًا من ذلك:

```text
TRAIN ───── VALIDATE ─ TEST
```

ثم تحريك النافذة:

```text
Train 2020-2022
Validation 2023
Test 2024

Train 2021-2023
Validation 2024
Test 2025
```

وهكذا.

يجب أن تكون الـOut-of-Sample النتائج منفصلة تمامًا عن الـtraining process.

---

# 15. Advanced Validation

بعد بناء Walk-Forward:

أضيفوا:

```text
Purged Cross Validation
Embargo
Monte Carlo Simulation
Parameter Stability Analysis
Sensitivity Analysis
Stress Testing
Regime-specific Evaluation
```

الهدف:

**إثبات Robustness وليس البحث عن Backtest جميل.**

---

# 16. Phase 4 — Strategy Engine

**الأولوية: High**

يجب ألا يكون النظام قائمًا على Strategy واحدة.

أنشئوا abstraction:

```python
BaseStrategy
```

وتدعم:

```text
Trend Following
Momentum
Mean Reversion
Breakout
Volatility
Statistical Arbitrage
AI-based Strategies
```

كل Strategy يجب أن تنتج Signal موحدًا:

```python
Signal(
    symbol,
    action,
    probability,
    confidence,
    timestamp,
    strategy_id,
    model_id,
    reason,
)
```

---

# 17. لا تجعلوا الـAI يولد Order مباشرة

النظام الصحيح:

```text
AI Model
    ↓
Probability / Forecast
    ↓
Signal
    ↓
Risk Engine
    ↓
Position Sizing
    ↓
Execution Engine
    ↓
Order
```

وليس:

```text
LLM → BUY AAPL 100 shares
```

---

# 18. Phase 5 — AI/ML Layer

**الأولوية: High**

ابدأوا من Models قابلة للقياس والمراجعة.

## المرحلة الأولى

ابدأوا بـ:

```text
XGBoost
LightGBM
CatBoost
Logistic Regression
Random Forest
```

ليس الهدف استخدام "أكثر موديل تعقيدًا".

الهدف:

> نموذج قوي + قابل للتفسير + مستقر + لا يعاني من overfitting.

---

# 19. AI Tasks

لا تجعلوا AI يحاول التنبؤ بالسعر مباشرة فقط.

اختبروا عدة Targets:

### Classification

```text
P(Return > threshold)
```

### Regression

```text
Expected return
```

### Volatility

```text
Expected volatility
```

### Regime

```text
Bull
Bear
Sideways
High Volatility
Low Volatility
Crisis
```

---

# 20. Regime Detection

هذه مكون أساسي.

أنشئوا:

```text
RegimeDetector
```

مثال:

```text
BULL
BEAR
SIDEWAYS
HIGH_VOL
LOW_VOL
CRISIS
```

ثم اربطوا الـregime بالاستراتيجية:

```text
Bull
→ Trend Following

Sideways
→ Mean Reversion

High Volatility
→ Reduce Position Size

Crisis
→ Risk-Off / No Trade
```

---

# 21. Ensemble Model

لا تعتمدوا على Model واحدة في القرار النهائي.

مثلاً:

```text
Trend Model
      +
Momentum Model
      +
Volatility Model
      +
Regime Model
      +
Technical Strategy
      ↓
Ensemble
      ↓
Final Probability
```

القرار النهائي يجب أن يحتوي:

```text
Signal
Probability
Confidence
Expected Return
Expected Risk
```

---

# 22. Phase 6 — Risk Engine

**الأولوية: Critical**

أنشئوا Risk Engine مستقل:

```text
risk/
├── manager.py
├── position_sizing.py
├── exposure.py
├── limits.py
├── drawdown.py
├── portfolio_risk.py
└── kill_switch.py
```

---

# 23. Pre-Trade Risk Checks

قبل كل أمر:

```text
Max Position Size
Max Daily Loss
Max Portfolio Exposure
Max Symbol Exposure
Max Sector Exposure
Max Leverage
Max Number of Open Positions
Max Order Value
Liquidity Limit
Volatility Limit
Correlation Limit
```

إذا فشل أي شرط:

```text
DO NOT TRADE
```

---

# 24. Position Sizing

لا تجعلوا القرار:

```text
BUY = fixed quantity
```

استخدموا position sizing حسب:

```text
Signal Confidence
Volatility
Account Size
Portfolio Exposure
Correlation
Maximum Risk per Trade
Drawdown State
```

الـPosition Size يجب أن يكون output من Risk Engine، وليس Strategy Engine.

---

# 25. Portfolio-Level Risk

النظام يجب أن ينظر إلى الـPortfolio وليس إلى Trade واحد.

يجب معرفة:

```text
Gross Exposure
Net Exposure
Sector Exposure
Factor Exposure
Correlation
Concentration
Portfolio Volatility
Portfolio Drawdown
```

ولا تفتحوا عدة صفقات تبدو مختلفة لكنها تتحرك فعليًا كأنها صفقة واحدة.

---

# 26. Kill Switch

أنشئوا `KillSwitch`.

يفعل النظام:

```text
STOP NEW ORDERS
```

في حالات مثل:

```text
Daily Loss Limit breached
Maximum Drawdown breached
Data feed stale
Broker disconnected
Unexpected position mismatch
Repeated order failures
Model service failure
Abnormal market conditions
System health failure
```

---

# 27. Phase 7 — Execution Engine

**الأولوية: Critical**

يجب إنشاء:

```text
execution/
├── engine.py
├── order_manager.py
├── execution_policy.py
├── slippage.py
├── reconciliation.py
└── idempotency.py
```

المسؤوليات:

```text
Signal → validate → risk → order → submit → monitor → reconcile
```

---

# 28. Broker Gateway

الـBroker adapters يجب أن تنفذ نفس الـcanonical interfaces.

لا يجب أن يعرف `Strategy` أي شيء عن:

```text
Alpaca SDK
Schwab SDK
IBKR SDK
```

الـStrategy تتعامل فقط مع domain models.

---

# 29. Real-time Architecture

لا تعتمدوا في الـlive system على polling فقط.

يجب دعم:

```text
WebSocket / Streaming
```

للبيانات عندما يكون ذلك متاحًا.

ويجب وجود:

```text
heartbeat
reconnect
backoff
stale-data detection
```

---

# 30. Phase 8 — LLM / Generative AI Layer

**الأولوية: Medium**

الـLLM لا يكون هو execution brain.

استخدموه كـIntelligence Layer.

## الاستخدامات المقترحة

```text
News classification
News summarization
Sentiment extraction
Event detection
Market commentary
Trade explanation
Post-trade analysis
Anomaly explanation
Research assistant
```

---

# 31. LLM Trade Context

يمكن أن ينتج:

```text
News Sentiment = -0.72
Event = Earnings Miss
Importance = High
Affected Symbol = XYZ
Confidence = 0.91
```

ثم يرسل ذلك إلى:

```text
Feature Engine / Signal Engine
```

ولا يرسل Order مباشرة إلى Broker.

---

# 32. Model Registry

أضيفوا Model Registry يحتوي:

```text
model_id
version
training_period
features_version
dataset_version
hyperparameters
metrics
validation_results
approval_status
deployment_status
```

لا تسمحوا بتشغيل نموذج جديد في الإنتاج بدون Version واضح.

---

# 33. Model Monitoring

راقبوا:

```text
Prediction Drift
Feature Drift
Data Drift
Confidence Drift
Performance Drift
Calibration
Error Rate
```

إذا تدهورت النتائج:

```text
ALERT
```

وليس:

```text
KEEP TRADING
```

بشكل أعمى.

---

# 34. Phase 9 — Paper / Shadow / Live Deployment

يمنع الانتقال المباشر:

```text
Backtest → Live
```

المراحل الإلزامية:

```text
Backtest
   ↓
Out-of-Sample
   ↓
Paper Trading
   ↓
Shadow Mode
   ↓
Very Small Capital
   ↓
Controlled Live
   ↓
Scale
```

---

# 35. Shadow Mode

في Shadow Mode:

النظام يقرر:

```text
BUY
```

لكنه لا يرسل الأمر.

يسجل:

```text
what would have happened
```

ثم تتم مقارنة:

```text
Expected execution
vs
Real market behavior
```

---

# 36. Observability

يجب بناء Dashboard تعرض:

```text
Account Equity
Daily P&L
Drawdown
Open Positions
Exposure
Orders
Fills
Rejected Orders
Latency
Model Confidence
Current Regime
Strategy Performance
Broker Health
Data Health
```

---

# 37. Audit Trail

كل قرار يجب أن يكون قابلًا لإعادة البناء.

سجلوا:

```text
timestamp
symbol
market state
features
model version
signal
confidence
risk decision
position size
order
broker response
fill
result
```

بحيث نستطيع الإجابة لاحقًا على:

> لماذا فتح النظام هذه الصفقة؟

---

# 38. Testing Strategy

يجب الحفاظ على الاختبارات الحالية وتوسيعها.

## Unit Tests

لكل:

```text
Indicator
Feature
Signal
Risk rule
Position sizing
Order normalization
Broker adapter
Execution rule
```

## Integration Tests

```text
Strategy
→ Risk
→ Execution
→ Paper Broker
```

## End-to-End

```text
Market Data
→ Strategy
→ Risk
→ Order
→ Fill
→ Portfolio
```

## Failure Tests

اختبروا:

```text
Broker outage
Network timeout
Duplicate response
Stale data
Bad market data
Partial fill
Rejected order
Unknown order state
Process restart
```

---

# 39. Security

ممنوع تخزين:

```text
API Keys
Broker Secrets
Tokens
Passwords
```

في:

```text
Git
Config committed files
Source code
Logs
```

استخدموا:

```text
Environment Variables
Secret Manager
Encrypted token storage
```

ويجب منع تسجيل الـsecrets في logs.

---

# 40. CI/CD

يجب أن يفشل الـpipeline إذا كان هناك:

```text
Tests failing
Type errors
Lint errors
Security vulnerabilities
Coverage regression
```

أضيفوا مستقبلًا:

```text
Mutation testing
Dependency scanning
Secret scanning
```

---

# 41. Definition of Done

لا تعتبروا أي Feature مكتملة لمجرد أن الكود يعمل.

Feature = Done عندما يوجد:

```text
Implementation
+
Unit tests
+
Integration tests
+
Error handling
+
Logging
+
Documentation
+
Metrics
+
Security review
```

---

# 42. ممنوعات مهمة

## ممنوع

إضافة عشرات المؤشرات بدون hypothesis.

## ممنوع

إضافة AI فقط لأجل التسويق.

## ممنوع

الاعتماد على LLM لإعطاء BUY/SELL بشكل مباشر.

## ممنوع

الاعتماد على Backtest واحد.

## ممنوع

اختيار أفضل Hyperparameters باستخدام نفس Test Set.

## ممنوع

استخدام بيانات مستقبلية.

## ممنوع

تشغيل Live Trading قبل Paper + Shadow.

## ممنوع

اعتبار Win Rate هو مقياس النجاح الرئيسي.

## ممنوع

توسيع رأس المال بعد أول نتائج إيجابية.

---

# 43. ترتيب الأولويات

نفذوا بالترتيب التالي:

```text
P0
Production Safety
Order Model
Broker correctness
Order lifecycle
Kill switch
Reconciliation
        ↓
P1
Data Quality
Data Layer
Backtesting realism
Walk Forward
OOS
        ↓
P2
Risk Engine
Position Sizing
Portfolio Risk
        ↓
P3
Strategy Engine
Regime Detection
        ↓
P4
ML Models
Ensemble
Model Registry
        ↓
P5
News / Sentiment
LLM Intelligence
        ↓
P6
Monitoring
Dashboard
Drift Detection
        ↓
P7
Paper
Shadow
Small Live
Controlled Scaling
```

---

# 44. المعيار الحقيقي لتقييم الاستراتيجية

لا تقبلوا Strategy جديدة لمجرد:

```text
Total Return > 0
```

يجب تقييم:

```text
OOS Return
Sharpe
Sortino
Calmar
Max Drawdown
Profit Factor
Expectancy
Turnover
Transaction Costs
Exposure
Stability
Regime Robustness
Parameter Robustness
Monte Carlo Drawdown
```

ويجب أن نعرف هل النتائج:

```text
Stable
```

أم:

```text
Dependent on a narrow date range
```

---

# 45. المطلوب من فريق التطوير قبل كل مرحلة

عند إنهاء كل Phase، قدموا تقريرًا يتضمن:

```text
1. What was implemented?
2. What files changed?
3. What assumptions were made?
4. What tests were added?
5. What tests passed?
6. What remains risky?
7. What performance impact exists?
8. What security implications exist?
9. What migration steps are required?
10. What is the next phase?
```

---

# 46. معيار المشروع النهائي

نريد الوصول إلى نظام له هذه الصفات:

```text
Reliable
Observable
Testable
Risk-controlled
Broker-agnostic
Data-driven
Model-aware
AI-assisted
Reproducible
Auditable
Scalable
```

وليس مجرد:

```text
BUY / SELL BOT
```

---

# 47. الخطة التنفيذية النهائية

## Sprint Group 1 — Stabilization

- [ ] Audit جميع Broker adapters.
- [ ] Canonical Order Model.
- [ ] Canonical Position Model.
- [ ] Order lifecycle.
- [ ] Idempotency.
- [ ] Retry policy.
- [ ] Reconciliation.
- [ ] Kill Switch.
- [ ] إصلاح أي order-state ambiguity.
- [ ] Regression tests.

## Sprint Group 2 — Data

- [ ] Data provider abstraction.
- [ ] Data normalization.
- [ ] Data quality validation.
- [ ] Historical data storage.
- [ ] Real-time data abstraction.
- [ ] Dataset versioning.

## Sprint Group 3 — Backtesting

- [ ] Event-driven engine.
- [ ] Realistic execution simulation.
- [ ] Slippage model.
- [ ] Spread model.
- [ ] Liquidity constraints.
- [ ] Partial fills.
- [ ] Transaction cost model.
- [ ] Walk-forward.
- [ ] OOS testing.
- [ ] Monte Carlo.

## Sprint Group 4 — Risk

- [ ] RiskManager.
- [ ] Position sizing.
- [ ] Portfolio exposure.
- [ ] Correlation limits.
- [ ] Drawdown control.
- [ ] Daily loss control.
- [ ] Circuit breaker.
- [ ] Kill switch.

## Sprint Group 5 — AI

- [ ] Feature Store.
- [ ] Dataset builder.
- [ ] XGBoost baseline.
- [ ] LightGBM baseline.
- [ ] Regime detector.
- [ ] Model evaluation.
- [ ] Ensemble.
- [ ] Probability calibration.
- [ ] Model registry.

## Sprint Group 6 — Intelligence

- [ ] News ingestion.
- [ ] Event classification.
- [ ] Sentiment extraction.
- [ ] LLM research layer.
- [ ] Trade explanation.
- [ ] Anomaly analysis.

## Sprint Group 7 — Production

- [ ] Monitoring.
- [ ] Dashboard.
- [ ] Alerts.
- [ ] Drift monitoring.
- [ ] Audit trail.
- [ ] Shadow mode.
- [ ] Paper trading validation.
- [ ] Small-capital rollout.

---

# 48. القرار النهائي للفريق

لا تعيدوا كتابة المشروع من الصفر.

استفيدوا من الـexisting architecture وخاصة:

```text
PyRobot
Portfolio
Trade
StockFrame
Indicators
BrokerInterface
PaperBroker
Backtesting
Testing
CI
```

لكن أعيدوا تنظيم المسؤوليات حول:

```text
Data
Research
Models
Strategies
Risk
Portfolio
Execution
Brokers
Monitoring
```

الهدف ليس زيادة حجم المشروع.

الهدف هو **رفع جودة القرارات وتقليل المخاطر التشغيلية والمنهجية**.

---

# 49. Final Engineering Directive

قبل كتابة أي Feature جديدة، اسألوا:

> هل هذه الإضافة تزيد قدرة النظام على اتخاذ قرار تداول أكثر موثوقية، أو تقلل المخاطر، أو تحسن جودة البيانات، أو تحسن التحقق التجريبي، أو تجعل التنفيذ أكثر أمانًا؟

إذا كانت الإجابة:

```text
NO
```

فلا تضيفوا الـFeature.

إذا كانت الإجابة:

```text
YES
```

فاشرحوا:

```text
Hypothesis
Expected Benefit
Risk
Metrics
Validation Method
Rollback Plan
```

ثم ابدؤوا التنفيذ.

---

# 50. الهدف النهائي

نريد بناء:

> **AI-assisted Quantitative Trading Platform**

وليس:

> **AI chatbot that tells the trader what to buy.**

الـAI يجب أن يكون جزءًا من منظومة Quant أكبر، بينما:

```text
Risk
+
Execution
+
Validation
+
Data Quality
+
Monitoring
```

هي التي تجعل النظام قابلًا للاستخدام الحقيقي.

**لا يوجد أي ضمان للربحية.**

المطلوب هندسيًا هو بناء نظام قادر على إثبات وجود Edge بصورة منهجية، ثم اختبار استمرار هذا الـEdge خارج العينة وتحت تكاليف التنفيذ والظروف المختلفة، قبل تعريض رأس المال للخطر.

---

## References داخل المشروع

- `PROJECT_REPORT.md`
- `README.md`
- `plan+1.md`
- `pyrobot/brokers/base.py`
- `pyrobot/brokers/alpaca_broker.py`
- `pyrobot/brokers/schwab_broker.py`
- `pyrobot/brokers/ibkr_broker.py`
- `pyrobot/backtesting/engine.py`
- `tests/test_backtesting.py`
- `pyproject.toml`

**End of Master Development Prompt**
