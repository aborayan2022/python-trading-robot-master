# AI Quant Trading Platform — Multi-Market Wave Directive

## الوثيقة التنفيذية الموجهة لفريق التطوير — التوسع إلى أسواق متعددة واستراتيجيات متنوعة

**Project:** `python-trading-robot-master`
**Target:** الانتقال من "سوق أمريكي واحد + استراتيجية واحدة" إلى **منصة متعددة الأسواق (أسهم/معادن/عملات رقمية) مع استراتيجيات ثنائية الاتجاه + منهج تعليمي متعدد الأسواق**
**Current Version:** `v0.2.0`
**Repository:** https://github.com/aborayan2022/python-trading-robot-master
**Prepared:** 2026-09-09
**Depends on:** `AI_Quant_Trading_Platform_Master_Development_Prompt.md` (الوثيقة الأساسية)

---

# 1. تعليمات عامة للفريق

هذه الوثيقة هي الامتداد التنفيذي للوثيقة الأساسية (`AI_Quant_Trading_Platform_Master_Development_Prompt.md`).她是etail التوسع من سوق أمريكي واحد واستراتيجية واحدة إلى منصة متعددة الأسواق.

**لا تنسخوا هذا العمل من الصفر.** الهدف هو توسيع المنصة الحالية بصورة متدرجة ومحسوبة، مع الحفاظ على كل ما تم بناؤه بصعوبة.

## القواعد الأساسية للتوسع

**القاعدة 1: Paper Trading فقط — لا Live Trading.**
ممنوع تشغيل التداول الحقيقي بأموال حقيقية لأي سوق جديد. الانتقال من Backtest إلى Paper Trading فقط.

**القاعدة 2: بيانات حقيقية و Benchmarking مقابل Buy & Hold.**
لا تقبلوا أي نتيجة backtest بدون مقارنتها مع أداء Market Buy & Hold. إذا كانت الاستراتيجية لا تتفوق على الشراء والاحتفاظ مع تكاليف التنفيذ، فلا داعي لها.

**القاعدة 3: قرار السوق الجديد قبل كتابة أي كود.**
قبل إضافة أي سوق جديد (معادن، عملات رقمية، أسهم مصرية)، يجب إصدار Decision Memo وفقًا لـ `docs/professional_development_standard.md:96-97`:

> "A new market (Egyptian, metals, crypto) or execution-layer change requires the NautilusTrader decision memo (Track 3 of the quarterly plan) before any code."

**القاعدة 4: درس موثق لكل سوق قبل التنفيذ.**
يجب تسجيل دورة تعليمية كاملة لكل سوق في `reports/continuous_research_log.md` قبل كتابة أي كود متعلق بهذا السوق.

**القاعدة 5: لا تقيسوا النجاح بعدد الأسواق أو الاستراتيجيات.**
المنصة التي تدعم 10 أسواق بنتائج ضعيفة أقل قيمة من منصة تدعم سوقًا واحدًا بإثبات Edge منهجي.

---

# 2. الحالة الحالية للمنصة (Team's Current State Snapshot)

يجب أن يعرف الفريق بدقة من أين نبدأ حتى لا نعيد اكتشاف ما تم بالفعل.

## 2.1 ما تم بناؤه بالفعل

| المكون | الملفات | الحالة |
|--------|---------|--------|
| Strategy Base Classes | `pyrobot/strategies/base.py` | `BaseStrategy` + `MultiSymbolStrategy` + `ExampleStrategy` — جاهز |
| US Trend Strategy | `pyrobot/strategies/us_trend.py:32` | `USTrendFollowStrategy(MultiSymbolStrategy)` — يعمل |
| Trading Pipeline | `pyrobot/runtime/pipeline.py` | `TradingPipeline` — متكامل: Data → Strategy → Risk → Execution → Audit |
| Trading Loop | `pyrobot/runtime/loop.py` | `TradingLoop` — جاهز |
| AI Ensemble | `pyrobot/ai/ensemble.py` | `EnsembleSignalEngine` — يعمل بدون Champion Model (الافتراضي `NO_TRADE`) |
| Backtesting Engine | `pyrobot/backtesting/engine.py` | `BacktestEngine` — جاهز |
| Cost Model | `pyrobot/backtesting/cost_model.py` | `ExecutionCostModel` — جاهز |
| Walk Forward | `pyrobot/backtesting/walk_forward.py` | جاهز مع Purge/Embargo |
| Monte Carlo | `pyrobot/backtesting/monte_carlo.py` | جاهز |
| Data Quality | `pyrobot/data/quality.py` | `DataQualityEngine` — 404 سطر، جاهز |
| Risk Engine | `pyrobot/risk/manager.py` + `kill_switch.py` + `circuit_breaker.py` | جاهز |
| Audit Ledger | `pyrobot/audit/ledger.py` | جاهز |
| Paper Broker | `pyrobot/brokers/paper_broker.py` | جاهز |
| Backtest Script | `us_strategy_backtest.py` | 500 سطر، يعمل مع 10 أسهم أمريكية |
| Paper Session Script | `us_paper_session.py` | 598 سطر، جلسة ورقية يومية |
| Strategy Test | `tests/test_us_trend_strategy.py` | 138 سطر، 5 اختبارات ناجحة |

## 2.2 نقاط التوسع المحددة (Identified Expansion Points)

| النقاط الناقصة | الملف / الموقع | التفاصيل |
|----------------|---------------|----------|
| **Fixed Universe: 10 أسهم أمريكية فقط** | `us_strategy_backtest.py:57`، `us_paper_session.py:56` | `DEFAULT_UNIVERSE` = 10 أسهم محددة — لا دعم لأي سوق آخر |
| **استراتيجية واحدة فقط** | `pyrobot/strategies/us_trend.py:32` | `USTrendFollowStrategy` — Long Only — لا Mean Reversion — لا Short |
| **لا Strategy Registry** | `pyrobot/runtime/pipeline.py` | التوصيل يدوي عبر `build_alpaca_pipeline` — لا Factory Pattern |
| **لا Data Provider للمعادن/العملات الرقمية** | `pyrobot/data/` | `alpaca.py` و `base.py` — مصممان لأسهم أمريكية فقط |
| **تقويم تداول أمريكي فقط** | `us_paper_session.py:28-30` | `PRE_CLOSE_START/END` = ET — لا دعم لـCrypto 24/7 |
| **بطاقتان "Coming Soon" في واجهة المستخدم** | `pyrobot/console/static/index.html:670-712` | IBKR و Crypto معطلتان |
| **سجل الدروس مركّز على الأسهم الأمريكية فقط** | `reports/continuous_research_log.md` | 4 entries — لا ذكر للمعادن أو العملات الرقمية |
| **لا ML Champion Model** | `pyrobot/ai/training.py` | Economic gate يرفض — الافتراضي `NO_TRADE` |

## 2.3 المعمارية الحالية Relevant للتوسع

```text
pyrobot/
├── strategies/
│   ├── base.py          ← BaseStrategy / MultiSymbolStrategy
│   └── us_trend.py      ← USTrendFollowStrategy (المثال الوحيد)
├── runtime/
│   ├── pipeline.py      ← TradingPipeline (يقبل BaseStrategy أو EnsembleSignalEngine)
│   └── loop.py          ← TradingLoop
├── data/
│   ├── base.py          ← Candle, MarketDataProvider (abstraction)
│   ├── alpaca.py        ← AlpacaProvider (أمريكي فقط)
│   └── quality.py       ← DataQualityEngine
├── ai/
│   ├── training.py      ← train_direction_champion_candidate
│   ├── ensemble.py      ← EnsembleSignalEngine
│   └── registry.py      ← Model Registry
├── backtesting/
│   ├── engine.py        ← BacktestEngine
│   ├── cost_model.py    ← ExecutionCostModel
│   ├── walk_forward.py  ← WalkForwardValidator
│   └── monte_carlo.py   ← MonteCarloSimulator
└── brokers/
    ├── paper_broker.py  ← PaperBroker
    └── base.py          ← BrokerInterface
```

---

# 3. الأهداف الاستراتيجية الخمسة (Five Strategic Goals)

## Goal A — التعليم متعدد الأسواق (Wave 0)

**الهدف:** بناء الأساس المعرفي قبل كتابة أي كود جديد.

**المطلوب:**

### A.1 منهج تعليمي في `docs/education/`

إنشاء 3 دروس تأسيسية — واحد لكل سوق:

```text
docs/education/
├── 01_stocks_foundations.md        ← الأسهم الأمريكية: الخصائص، ساعات التداول، التكاليف، المخاطر
├── 02_metals_foundations.md        ← المعادن الثمينة: الفروقات عن الأسهم، تأثير الدولار، عوامل العرض والطلب
├── 03_crypto_foundations.md        ← العملات الرقمية: اللامركزية، تقلباتها العالية، الاست썽اد، دورة 24/7
├── glossary_ar_en.md              ← مصطلحات عربية/إنجليزية مشتركة
├── 04_strategy_trend_follow.md    ← Trend Following: المنطق قبل الكود
├── 05_strategy_mean_reversion.md  ← Mean Reversion: المنطق قبل الكود
└── 06_strategy_breakout.md        ← Breakout: المنطق قبل الكود
```

كل درس يحتوي:
- خصائص السوق وأ ساعاته وتكاليفه ومخاطره
- لماذا هذه الاستراتيجية مناسبة لهذا السوق تحديدًا
- مثال وهمي على القرار قبل كتابة أي سطر كود

### A.2 مصطلحات عربية/إنجليزية

ملف `docs/education/glossary_ar_en.md` يحتوي:

| عربي | English | التعريف |
|------|---------|---------|
| اتجاه التداول | Trend Following | شراء عند الصعود، بيع عند الهبوط |
| المعيارية | Mean Reversion | الشراء عند الانخفاض، البيع عند الارتفاع |
| الاندفاع | Momentum | استمرار الزخم في اتجاه واحد |
| الاختراق | Breakout | تجاوز السعر لمستوى مقاومة أو دعم |
| التمويه | Slippage | الفرق بين السعر المتوقع والسعر الفعلي |
| نموذج التكلفة | ExecutionCostModel | محاكاة التكاليف الحقيقية |
| البوابة الاقتصادية | Economic Gate | فحص الأداء مقابل Benchmark قبل القبول |

### A.3 درس لكل استراتيجية جديدة

قبل كتابة كود أي استراتيجية جديدة، يجب كتابة درس يشرح المنطق والفرضية والأولويات.

### A.4 دخول لكل سوق في سجل البحوث

إضافة entry في `reports/continuous_research_log.md` لكل سوق جديد — يحتوي على:
- Sources ( YMMA, COMEX, Binance docs)
- Findings (خصائص السوق)
- Decision / Lesson
- Impact on code

### A.5 بطاقة تعليمية لكل سوق في الواجهة

تفعيل البطاقات في `pyrobot/console/static/index.html` — تحويل "Coming Soon" إلى بطاقة تعليمية تفاعلية.

---

## Goal B — طبقة البيانات متعددة الأسواق (Wave 1)

**الهدف:** بناء Data Provider يدعم أسهم + معادن + عملات رقمية.

**المطلوب:**

### B.1 Multi-Market Data Provider

```text
pyrobot/data/
├── base.py              ← MarketDataProvider (موجود — يحتاج Extension)
├── alpaca.py            ← AlpacaProvider (أمريكي — موجود)
├── metals_provider.py   ← MetalsProvider (جديد)
├── crypto_provider.py   ← CryptoProvider (جديد)
└── registry.py          ← DataProviderRegistry (جديد)
```

### B.2 المعادن الثمينة عبر yfinance

| الرمز | الوصف | المصدر |
|-------|-------|--------|
| `GC=F` | Gold Futures | yfinance |
| `SI=F` | Silver Futures | yfinance |
| `GLD` | SPDR Gold Trust ETF | yfinance |
| `SLV` | iShares Silver Trust ETF | yfinance |
| `PL=F` | Platinum Futures | yfinance |
| `PA=F` | Palladium Futures | yfinance |

### B.3 العملات الرقمية عبر yfinance / CCXT

| الرمز | الوصف | المصدر |
|-------|-------|--------|
| `BTC-USD` | Bitcoin | yfinance (أولوية) |
| `ETH-USD` | Ethereum | yfinance (أولوية) |
| `SOL-USD` | Solana | yfinance / CCXT |
| `BNB-USD` | Binance Coin | CCXT |

**ملاحظة:** CCXT هو الخيار البديل إذا أردنا دعم Real-time و Frame-by-frame — لكن يبدأ بـ yfinance للبساطة.

### B.4 التخزين

```text
data/
├── us_market/           ← موجود (10 أسهم CSV)
├── metals/              ← جديد
│   ├── GC=F.csv
│   ├── SI=F.csv
│   └── ...
├── crypto/              ← جديد
│   ├── BTC-USD.csv
│   ├── ETH-USD.csv
│   └── ...
└── reports/             ← موجود (سيتم توسيعه)
```

### B.5 تقويمات التداول

| السوق | التقويم | ملاحظات |
|--------|---------|---------|
| أسهم أمريكية | NYSE: 9:30-16:00 ET | موجود بالفعل |
| معادن | COMEX: 9:00-14:30 ET + Globex | أقرب إلى ساعات الأسهم |
| عملات رقمية | **24/7/365** | لا إغلاق — لا holiday — لا after-hours |

### B.6 فحص جودة البيانات لكل سوق

توسيع `pyrobot/data/quality.py` ليدعم:
- اكتشاف الثغرات الزمنية حسب تقويم السوق
- التحقق من relationships OHLC لكل سوق
- فحص الstaleness حسب trading hours

---

## Goal C — حزمة الاستراتيجيات (Wave 2)

**الهدف:** بناء Strategy Registry و 2-3 استراتيجيات لكل سوق تغطي كلا الاتجاهين.

**المطلوب:**

### C.1 Strategy Registry (Factory Pattern)

```text
pyrobot/strategies/
├── base.py              ← BaseStrategy / MultiSymbolStrategy (موجود)
├── registry.py          ← StrategyRegistry (جديد)
├── us_trend.py          ← USTrendFollowStrategy (موجود)
├── us_mean_reversion.py ← USMeanReversionStrategy (جديد)
├── us_breakout.py       ← USBreakoutStrategy (جديد)
├── metals_trend.py      ← MetalsTrendFollowStrategy (جديد)
├── metals_momentum.py   ← MetalsMomentumBreakout (جديد)
├── crypto_trend.py      ← CryptoTrendBreakoutStrategy (جديد)
└── crypto_mean_rev.py   ← CryptoMeanReversionStrategy (جديد)
```

### C.2 Strategy Registry Pattern

```python
# pyrobot/strategies/registry.py
class StrategyRegistry:
    """Factory for creating strategy instances by name."""

    _registry: Dict[str, Type[BaseStrategy]] = {}

    @classmethod
    def register(cls, name: str, strategy_class: Type[BaseStrategy]) -> None:
        cls._registry[name] = strategy_class

    @classmethod
    def create(cls, name: str, symbols: List[str], parameters: Dict = None) -> BaseStrategy:
        if name not in cls._registry:
            raise ValueError(f"Unknown strategy: {name}. Available: {list(cls._registry.keys())}")
        return cls._registry[name](strategy_id=name, symbols=symbols, parameters=parameters)

    @classmethod
    def available(cls) -> List[str]:
        return list(cls._registry.keys())
```

**الاختيار عبر Environment Variables:**

```bash
PYROBOT_STRATEGY=us_trend
PYROBOT_MARKET=us
PYROBOT_UNIVERSE=AAPL,MSFT,GOOGL
```

### C.3 خطة الاستراتيجيات لكل سوق

#### أسهم أمريكية (US Stocks)

| الاستراتيجية | الاتجاه | الملف | الحالة |
|---------------|---------|-------|--------|
| `USTrendFollowStrategy` | Long Only | `us_trend.py` | ✅ موجود |
| `USMeanReversionStrategy` | Long + Short | `us_mean_reversion.py` | 🔨 جديد |
| `USBreakoutStrategy` | Long + Short | `us_breakout.py` | 🔨 جديد |

**US Mean Reversion:** شراء عند انحراف RSI عن المعيارية، بيع عند العودة. Short عند انحراف عالي.
**US Breakout:** شراء عند اختراق High+ATR، Short عند اختراق Low-ATR.

#### المعادن (Metals)

| الاستراتيجية | الاتجاه | الملف | الحالة |
|---------------|---------|-------|--------|
| `MetalsTrendFollowStrategy` | Long + Short | `metals_trend.py` | 🔨 جديد |
| `MetalsMomentumBreakout` | Long + Short | `metals_momentum.py` | 🔨 جديد |

**Metals Trend:** اتجاهي طويل المدى مع تأثير قوي لـ SMA-50/200. Short عند هبوط السعر تحت Moving Average مع تأكيد Momentum.
**Metals Momentum:** كسر مستويات مع تأكيد حجم التداول والتقلبات.

#### العملات الرقمية (Crypto)

| الاستراتيجية | الاتجاه | الملف | الحالة |
|---------------|---------|-------|--------|
| `CryptoTrendBreakoutStrategy` | Long + Short | `crypto_trend.py` | 🔨 جديد |
| `CryptoMeanReversionStrategy` | Long + Short | `crypto_mean_rev.py` | 🔨 جديد |

**Crypto Trend/Volatility Breakout:** استراتيجية اتجاهية تتغير مع تقلبات عالية. Short عند انهيار السعر تحت Bollinger Lower مع ارتفاع Volume.
**Crypto Mean Reversion:** استغلال الارتداد السريع في الأسواق المتقلبة. شراء عند انخفاض RSI الشديد، بيع عند الارتداد.

### C.4 كل استراتيجية تُبنى باستخدام BaseStrategy/MultiSymbolStrategy

```python
# النمط المطلوب لكل استراتيجية جديدة
class MetalsTrendFollowStrategy(MultiSymbolStrategy):
    DEFAULT_PARAMETERS = {
        "sma_fast": 50,
        "sma_slow": 200,
        "rsi_period": 14,
        "rsi_enter_min": 30,
        "rsi_enter_max": 70,
        "max_atr_pct": 0.05,
    }

    def initialize(self) -> None: ...
    def on_bar(self, symbol: str, bar: dict, stock_frame: StockFrame) -> Signal: ...
    def on_order_fill(self, order_dict: dict) -> None: ...
```

### C.5 ممنوعات الاستراتيجيات

- **ممنوع** أن تضع منطق الـrisk داخل الـstrategy
- **ممنوع** أن تجعل الـstrategy تتداول بشكل مباشر مع Broker
- **ممنوع** أن ت WESTER disciplined position sizing — هذا دور Risk Engine
- **ممنوع** أن تبني استراتيجية جديدة بدون درس في `docs/education/`

---

## Goal D — الاختبار والتحقق (Wave 3)

**الهدف:** اختبار كل استراتيجية في كل سوق مع تكاليف حقيقية ومقارنة مع Buy & Hold.

**المطلوب:**

### D.1 Backtesting لكل استراتيجية/سوق

**النمط:** اتباع نمط `us_strategy_backtest.py` (500 سطر)

```text
backtest_<market>_<strategy>.py
├── US Mean Reversion Backtest
├── US Breakout Backtest
├── Metals Trend Backtest
├── Metals Momentum Backtest
├── Crypto Trend Backtest
└── Crypto Mean Reversion Backtest
```

كل backtest يحتوي:
- **Primary honest backtest** — ملء عند next bar open عبر `ExecutionCostModel`
- **Runtime replay** عبر `TradingPipeline` + `TradingLoop`
- **Benchmark** مقابل Buy & Hold
- **真实的 تكاليف** (spread, slippage, commission)

### D.2 Paper Trading Session لكل سوق

**النمط:** اتباع نمط `us_paper_session.py` (598 سطر)

```text
paper_session_<market>.py
├── metals_paper_session.py   ← مع تقويم COMEX
└── crypto_paper_session.py   ← مع تقويم 24/7
```

كل جلسة paper trading:
- **Real broker adapter** (PaperBroker لل模拟)
- **Market-specific timezone** (ET for metals, UTC for crypto)
- **Audit trail** كامل
- **Risk monitoring** مستمر

### D.3 التقارير

```text
data/reports/
├── us_paper_session_*.json          ← موجود
├── metals_backtest_*.json           ← جديد
├── metals_paper_session_*.json      ← جديد
├── crypto_backtest_*.json           ← جديد
├── crypto_paper_session_*.json      ← جديد
└── multi_market_comparison.json     ← جديد (مقارنة شاملة)
```

### D.4 Audit Log Expansion

توسيع `data/audit/` ليدعم:
```text
data/audit/
├── ledger.jsonl               ← موجود
├── metals_paper_session_*.jsonl  ← جديد
└── crypto_paper_session_*.jsonl  ← جديد
```

---

## Goal E — نشر جميع الأدوات (Wave 4)

**الهدف:** تدريب ML لكل سوق، تحليلات متقدمة، وتفعيل الواجهة.

**المطلوب:**

### E.1 ML Training لكل سوق

توسيع `pyrobot/ai/training.py` ليدعم:
- **Training per market** — نموذج منفصل لكل سوق
- **Governance gateways** — Economic gate لكل نموذج
- **Walk-forward + Monte Carlo** لكل نموذج
- **Model registry** يدعم multiple markets

### E.2 Regime Detection لكل سوق

توسيع `pyrobot/features/regime.py` ليدعم:
- Regime detection لكل سوق (Bull/Bear/Sideways/High Vol/Crisis)
- ربط Regime بالاستراتيجية المناسبة لكل سوق
- Regime-specific position sizing

### E.3 توسيع Weekly Research Script

توسيع `scripts/weekly_research.py` ليتحقق من:
- Benchmarking لكل سوق (Buy & Hold comparison)
- أداء كل استراتيجية مقابل سوقها
- Upgrades في المكتبات المرجعية

### E.4 تفعيل بطاقات الأسواق في الواجهة

```text
pyrobot/console/static/index.html
├── Alpaca card    ← موجود (مفعل)
├── IBKR card      ← Coming Soon (يجب تفعيله أو إزالته)
├── Metals card    ← جديد (مفعل)
└── Crypto card    ← Coming Soon → مفعل
```

### E.5 CI و Docker Compose

توسيع `docker-compose.yml` و CI pipeline لدعم:
- اختبارات لكل سوق
- Backtesting لكل سوق
- Paper trading لكل سوق

### E.6 التقرير الاستشاري النهائي

```text
reports/
└── AI_Quant_Multi_Market_Advisory_Report.md  ← تقرير شامل لحالة المنصة
```

---

# 4. الأمواج مع معايير القبول القابلة للقياس (Waves with Acceptance Criteria)

## Wave 0 — التعليم (Goal A)

### معايير القبول

| # | المعيار | كيف نتحقق |
|---|---------|-----------|
| 0.1 | ملفات الدروس الثلاثة موجودة في `docs/education/` | `ls docs/education/*.md` |
| 0.2 | كل درس يحتوي: الخصائص، الساعات، التكاليف، المخاطر | مراجعة يدوية |
| 0.3 | ملف المصطلحات العربي/الإنجليزي موجود | `ls docs/education/glossary_ar_en.md` |
| 0.4 | 3 دروس للم strategies جديدة موجودة | `ls docs/education/04_*.md 05_*.md 06_*.md` |
| 0.5 | entry لكل سوق في `continuous_research_log.md` | `grep "Metals\|Crypto" reports/continuous_research_log.md` |
| 0.6 | بطاقة لكل سوق في الواجهة | `grep -c "card" pyrobot/console/static/index.html` |
| 0.7 | لا كود جديد مكتوب في هذا الموج | `git diff --stat` — لا ملفات `.py` جديدة |

---

## Wave 1 — طبقة البيانات (Goal B)

### معايير القبول

| # | المعيار | كيف نتحقق |
|---|---------|-----------|
| 1.1 | `MetalsProvider` موجود في `pyrobot/data/metals_provider.py` | `ls pyrobot/data/metals_provider.py` |
| 1.2 | `CryptoProvider` موجود في `pyrobot/data/crypto_provider.py` | `ls pyrobot/data/crypto_provider.py` |
| 1.3 | `DataProviderRegistry` موجود في `pyrobot/data/registry.py` | `ls pyrobot/data/registry.py` |
| 1.4 | البيانات المحفوظة في `data/metals/` و `data/crypto/` | `ls data/metals/ data/crypto/` |
| 1.5 | تقويم 24/7 للعملات الرقمية يعمل | `python -c "from pyrobot.data.crypto_provider import CryptoProvider; print(CryptoProvider.TRADING_CALENDAR)"` |
| 1.6 | `DataQualityEngine` يدعم فحص جودة لكل سوق | اختبارات جديدة في `tests/test_data_quality_multi_market.py` |
| 1.7 | اختبارات ناجحة: `pytest tests/test_data_quality_multi_market.py -v` | Exit code 0 |
| 1.8 | لا اختبارات حالية مكسورة: `pytest tests/ -v` | Exit code 0 |

---

## Wave 2 — حزمة الاستراتيجيات (Goal C)

### معايير القبول

| # | المعيار | كيف نتحقق |
|---|---------|-----------|
| 2.1 | `StrategyRegistry` موجود ويعمل | `ls pyrobot/strategies/registry.py` |
| 2.2 | 3 استراتيجيات أمريكية جديدة موجودة | `ls pyrobot/strategies/us_*.py` |
| 2.3 | استراتيجيتا معادن موجودتان | `ls pyrobot/strategies/metals_*.py` |
| 2.4 | استراتيجيتا عملات رقمية موجودتان | `ls pyrobot/strategies/crypto_*.py` |
| 2.5 | كل استراتيجية ترث من `MultiSymbolStrategy` | `grep -l "MultiSymbolStrategy" pyrobot/strategies/*.py` |
| 2.6 | كل استراتيجية لها `DEFAULT_PARAMETERS` | `grep -l "DEFAULT_PARAMETERS" pyrobot/strategies/*.py` |
| 2.7 | كل استراتيجية لها اختبار على نمط `test_us_trend_strategy.py` | `ls tests/test_*_strategy.py` |
| 2.8 | اختبارات ناجحة: `pytest tests/test_*_strategy.py -v` | Exit code 0 |
| 2.9 | لا اختبارات حالية مكسورة | `pytest tests/ -v` | Exit code 0 |
| 2.10 | `StrategyRegistry` يدعم الاختيار عبر env vars | اختبار وحدة يثبت ذلك |

---

## Wave 3 — الاختبار والتحقق (Goal D)

### معايير القبول

| # | المعيار | كيف نتحقق |
|---|---------|-----------|
| 3.1 | Backtest script لكل استراتيجية/سوق موجود | `ls backtest_*.py` |
| 3.2 | كل backtest يقارن مع Buy & Hold | `grep -l "buy_and_hold\|benchmark" backtest_*.py` |
| 3.3 | كل backtest يستخدم `ExecutionCostModel` | `grep -l "ExecutionCostModel" backtest_*.py` |
| 3.4 | Paper trading session لكل سوق موجود | `ls *_paper_session.py` |
| 3.5 | تقارير backtest في `data/reports/` | `ls data/reports/*backtest*.json` |
| 3.6 | تقارير paper session في `data/reports/` | `ls data/reports/*paper*.json` |
| 3.7 | Audit log لكل سوق | `ls data/audit/*paper*.jsonl` |
| 3.8 | كل backtest يمر بدون أخطاء | `python backtest_*.py --dry-run` |
| 3.9 | كل paper session يمر بدون أخطاء | `python *_paper_session.py --smoke` |
| 3.10 | لا اختبارات حالية مكسورة | Exit code 0 |

---

## Wave 4 — نشر جميع الأدوات (Goal E)

### معايير القبول

| # | المعيار | كيف نتحقق |
|---|---------|-----------|
| 4.1 | ML training يدعم multiple markets | `grep -l "market" pyrobot/ai/training.py` |
| 4.2 | Walk-forward + Monte Carlo لكل استراتيجية | `python -c "from pyrobot.backtesting.walk_forward import WalkForwardValidator; print('OK')"` |
| 4.3 | Regime detection لكل سوق | `grep -l "regime" pyrobot/features/regime.py` |
| 4.4 | Weekly research script يتحقق من benchmarks متعددة | `grep -l "benchmark\|multi_market" scripts/weekly_research.py` |
| 4.5 | بطاقات الأسواق مفعلة في الواجهة | لا "Coming Soon" في metals/crypto |
| 4.6 | CI يمر مع جميع الاختبارات | `pytest tests/ -v` exit code 0 |
| 4.7 | Docker Compose يعمل لكل سوق | `docker-compose config` |
| 4.8 | التقرير الاستشاري النهائي موجود | `ls reports/AI_Quant_Multi_Market_Advisory_Report.md` |
| 4.9 | لا Live Trading في أي مكان | `grep -r "live_trading\|LIVE" pyrobot/ --include="*.py" | grep -v "comment\|docstring\|test"` = فارغ |
| 4.10 | لا bypass للGovernance | `grep -r "skip_gate\|bypass.*gate" pyrobot/ --include="*.py"` = فارغ |

---

# 5. ممنوعات (Prohibitions)

## ممنوعات مطلقة

| # | الممنوع | السبب |
|---|---------|-------|
| 1 | **تشغيل Live Trading بأموال حقيقية لأي سوق** | الانتقال من Backtest → Paper فقط |
| 2 | **تجاوز Governance Gateway** | كل نموذج ML يجب أن يمر عبر Economic Gate في `pyrobot/ai/training.py` |
| 3 | **اختيار أفضل Hyperparameters باستخدام نفس Test Set** | Overfitting — استخدم Walk-Forward فقط |
| 4 | **بناء Data Provider من الصفر بدلاً من yfinance/CCXT** | reinventing — استخدم المكتبات المختبرة |
| 5 | **إضافة أسواق جديدة بدون Decision Memo** | `docs/professional_development_standard.md:96-97` |
| 6 | **كتابة كود استراتيجية بدون درس في `docs/education/`** | Research Before Building |
| 7 | **جعل AI يولد Order مباشرة** | AI → Signal → Risk → Position Sizing → Execution |
| 8 | **تجاهل Buy & Hold Benchmark** | كل استراتيجية يجب أن تتفوق على الشراء والاحتفاظ |
| 9 | **إضافة 100 strategy بدون اختبار واحد** | جودة فوق الكمية |
| 10 | **استخدام بيانات مستقبلية (Look-ahead Bias)** | 다음 bar open فقط |

---

# 6. بنية التقارير المطلوبة بعد كل موجة

بعد إنهاء كل موجة، قدموا تقريرًا يتضمن:

```text
1. ما تم تنفيذه؟ (What was implemented?)
2. أي ملفات تغيرت؟ (What files changed?)
3. أي افتراضات صُنعت؟ (What assumptions were made?)
4. أي اختبارات أُضيفت؟ (What tests were added?)
5. أي اختبارات نجحت؟ (What tests passed?)
6. ما الذي لا يزال محفوفًا بالمخاطر؟ (What remains risky?)
7. أي تأثيرات على الأداء؟ (What performance impact exists?)
8. أي تأثيرات على الأمان؟ (What security implications exist?)
9. أي خطوات ترحيل مطلوبة؟ (What migration steps are required?)
10. ما الموجة التالية؟ (What is the next wave?)
```

---

# 7. المعيار النهائي للمنصة متعددة الأسواق

لا نريد منصة تدعم 10 أسواق بنتائج ضعيفة.

نريد منصة تدعم:
- 3 أسواق (أسهم + معادن + عملات رقمية)
- 7+ استراتيجيات (تغطي Long و Short)
- اثبات Edge منهجي لكل استراتيجية/سوق
- مقارنة صادقة مع Buy & Hold
- تكاليف تنفيذ حقيقية
- رؤية كاملة لكل قرار

المنصة النهائية يجب أن تكون:

```text
Multi-Market
Multi-Strategy
Bi-Directional (Long + Short)
Cost-Adjusted
Benchmark-Compared
Regime-Aware
Risk-Controlled
Audit-Trailed
Paper-Tested (NOT Live)
```

وليس مجرد:

```text
100 strategy scripts that nobody tested properly.
```

---

# 8. Appendices — أوامر جاهزة للنسخ واللصق (Copy-Paste Ready Prompts)

## Appendix A — Wave 0 Prompt (التعليم)

```markdown
# Wave 0: Multi-Market Education Curriculum

## Context
المنصة حاليًا تدعم سوقًا واحدًا (أسهم أمريكية) واستراتيجية واحدة (USTrendFollowStrategy).
قبل كتابة أي كود جديد، نبني الأساس المعرفي لكل سوق وstrategy.

## Reference Files
- `docs/professional_development_standard.md` — Research Before Building
- `reports/continuous_research_log.md` — سجل البحوث
- `pyrobot/strategies/us_trend.py` — الاستراتيجية الحالية
- `pyrobot/console/static/index.html:670-712` — البطاقات Coming Soon

## Tasks
1. أنشئ `docs/education/01_stocks_foundations.md` — درس أسهم أمريكية
2. أنشئ `docs/education/02_metals_foundations.md` — درس معادن
3. أنشئ `docs/education/03_crypto_foundations.md` — درس عملات رقمية
4. أنشئ `docs/education/glossary_ar_en.md` — مصطلحات عربية/إنجليزية
5. أنشئ `docs/education/04_strategy_trend_follow.md` — منطق Trend Following
6. أنشئ `docs/education/05_strategy_mean_reversion.md` — منطق Mean Reversion
7. أنشئ `docs/education/06_strategy_breakout.md` — منطق Breakout
8. أضف entry لكل سوق في `reports/continuous_research_log.md`
9. حسّن البطاقات في `pyrobot/console/static/index.html` (Metals + Crypto)

## Outputs
- 7 ملفات تعليمية في `docs/education/`
- 3 entries جديدة في `continuous_research_log.md`
- بطاقات محسّنة في الواجهة

## Acceptance Criteria
- لا كود `.py` جديد في هذا الموج
- كل درس يحتوي: الخصائص، الساعات، التكاليف، المخاطر
- مصطلحات عربية/إنجليزية مشتركة
```

---

## Appendix B — Wave 1 Prompt (طبقة البيانات)

```markdown
# Wave 1: Multi-Market Data Layer

## Context
المنصة حاليًا تعتمد على `pyrobot/data/alpaca.py` للأسهم الأمريكية فقط.
نحتاج Data Providers للمعادن والعملات الرقمية.

## Reference Files
- `pyrobot/data/base.py` — MarketDataProvider abstraction
- `pyrobot/data/alpaca.py` — AlpacaProvider (النمط المطلوب)
- `pyrobot/data/quality.py` — DataQualityEngine (404 سطر)
- `pyrobot/data/storage.py` — التخزين
- `us_strategy_backtest.py:57` — DEFAULT_UNIVERSE

## Tasks
1. أنشئ `pyrobot/data/metals_provider.py`
   - MetalsProvider يدعم: GC=F, SI=F, GLD, SLV
   - استخدام yfinance
   - تخزين في `data/metals/`
   - تقويم COMEX
2. أنشئ `pyrobot/data/crypto_provider.py`
   - CryptoProvider يدعم: BTC-USD, ETH-USD
   - استخدام yfinance (أولوية)
   - تخزين في `data/crypto/`
   - تقويم 24/7
3. أنشئ `pyrobot/data/registry.py`
   - DataProviderRegistry يدعم تسجيل واستدعاء Providers
   - الاختيار عبر env vars: PYROBOT_MARKET
4. حسّن `pyrobot/data/quality.py`
   - دعم فحص جودة لكل سوق
   - تقويمات مختلفة
5. أنشئ `tests/test_data_quality_multi_market.py`
   - اختبارات لكل Data Provider
   - اختبارات جودة البيانات لكل سوق
6. حدّث `us_strategy_backtest.py` ليدعم اختيار السوق عبر env var

## Outputs
- 3 ملفات جديدة في `pyrobot/data/`
- ملف اختبارات جديد
- بيانات محفوظة في `data/metals/` و `data/crypto/`

## Acceptance Criteria
- `pytest tests/test_data_quality_multi_market.py -v` — Exit code 0
- `pytest tests/ -v` — لا اختبارات مكسورة
- بيانات معادن وعملات رقمية محفوظة
```

---

## Appendix C — Wave 2 Prompt (حزمة الاستراتيجيات)

```markdown
# Wave 2: Strategy Suite + Strategy Registry

## Context
المنصة حاليًا بها استراتيجية واحدة فقط: `USTrendFollowStrategy` (Long Only).
نحتاج 2-3 استراتيجيات لكل سوق تغطي كلا الاتجاهين.

## Reference Files
- `pyrobot/strategies/base.py` — BaseStrategy / MultiSymbolStrategy
- `pyrobot/strategies/us_trend.py` — النمط المطلوب
- `tests/test_us_trend_strategy.py` — نمط الاختبار
- `pyrobot/runtime/pipeline.py` — TradingPipeline (يقبل BaseStrategy)
- `pyrobot/models/signal.py` — Signal, SignalAction

## Tasks
1. أنشئ `pyrobot/strategies/registry.py`
   - StrategyRegistry مع Factory Pattern
   - تسجيل و استدعاء Strategies
   - الاختيار عبر PYROBOT_STRATEGY env var
2. أنشئ الاستراتيجيات الأمريكية:
   - `pyrobot/strategies/us_mean_reversion.py` — USMeanReversionStrategy
   - `pyrobot/strategies/us_breakout.py` — USBreakoutStrategy
3. أنشئ استراتيجيات المعادن:
   - `pyrobot/strategies/metals_trend.py` — MetalsTrendFollowStrategy
   - `pyrobot/strategies/metals_momentum.py` — MetalsMomentumBreakout
4. أنشئ استراتيجيات العملات الرقمية:
   - `pyrobot/strategies/crypto_trend.py` — CryptoTrendBreakoutStrategy
   - `pyrobot/strategies/crypto_mean_rev.py` — CryptoMeanReversionStrategy
5. أنشئ اختبارات لكل استراتيجية على نمط `test_us_trend_strategy.py`
6. حسّن `pyrobot/strategies/__init__.py` لتصدير الاستراتيجيات الجديدة

## Outputs
- `pyrobot/strategies/registry.py`
- 6 ملفات استراتيجيات جديدة
- 6 ملفات اختبارات جديدة

## Acceptance Criteria
- `pytest tests/test_*_strategy.py -v` — Exit code 0
- `pytest tests/ -v` — لا اختبارات مكسورة
- كل استراتيجية ترث من MultiSymbolStrategy
- كل استراتيجية لها DEFAULT_PARAMETERS
- StrategyRegistry يدعم الاختيار عبر env vars
```

---

## Appendix D — Wave 3 Prompt (الاختبار والتحقق)

```markdown
# Wave 3: Backtesting + Paper Trading per Market

## Context
لدينا الآن Strategies لكل سوق. نحتاج اختبارها بأمان مع تكاليف حقيقية ومقارنة مع Buy & Hold.

## Reference Files
- `us_strategy_backtest.py` — النمط المطلوب (500 سطر)
- `us_paper_session.py` — النمط المطلوب (598 سطر)
- `pyrobot/backtesting/cost_model.py` — ExecutionCostModel
- `pyrobot/backtesting/walk_forward.py` — WalkForwardValidator
- `pyrobot/backtesting/monte_carlo.py` — MonteCarloSimulator
- `data/reports/` — التقارير

## Tasks
1. أنشئ backtest scripts لكل استراتيجية/سوق:
   - `backtest_us_mean_reversion.py`
   - `backtest_us_breakout.py`
   - `backtest_metals_trend.py`
   - `backtest_metals_momentum.py`
   - `backtest_crypto_trend.py`
   - `backtest_crypto_mean_rev.py`
2. كل backtest يحتوي:
   - Honest backtest مع next bar open
   - ExecutionCostModel
   - Buy & Hold benchmark
   - Runtime replay عبر TradingPipeline
3. أنشئ paper trading sessions:
   - `metals_paper_session.py` (COMEX hours)
   - `crypto_paper_session.py` (24/7)
4. حسّث التقارير في `data/reports/`
5. حسّث Audit logs في `data/audit/`
6. شغّل كل backtest بـ `--dry-run` للتحقق
7. شغّل كل paper session بـ `--smoke` للتحقق

## Outputs
- 6 backtest scripts جديدة
- 2 paper session scripts جديدة
- تقارير جديدة في `data/reports/`
- Audit logs جديدة في `data/audit/`

## Acceptance Criteria
- كل backtest يمر بدون أخطاء (dry-run)
- كل paper session يمر بدون أخطاء (smoke)
- كل backtest يقارن مع Buy & Hold
- كل backtest يستخدم ExecutionCostModel
- لا اختبارات حالية مكسورة
```

---

## Appendix E — Wave 4 Prompt (نشر جميع الأدوات)

```markdown
# Wave 4: ML Training, Regime Detection, and Full Deployment

## Context
لدينا الآن اختبارات وdata وstrategies لكل سوق. نحتاج ML وregime detection وتفعيل الواجهة.

## Reference Files
- `pyrobot/ai/training.py` — train_direction_champion_candidate
- `pyrobot/ai/ensemble.py` — EnsembleSignalEngine
- `pyrobot/ai/registry.py` — Model Registry
- `pyrobot/features/regime.py` — Regime Detection
- `scripts/weekly_research.py` — Weekly Research
- `pyrobot/console/static/index.html` — الواجهة
- `docker-compose.yml` — Docker
- `.github/workflows/` أو `pyproject.toml` — CI

## Tasks
1. حسّن ML training لدعم multiple markets:
   - Training per market
   - Economic gate لكل نموذج
   - Model registry يدعم multiple markets
2. حسّن Walk-Forward + Monte Carlo لكل استراتيجية
3. حسّن Regime Detection لكل سوق
4. حسّن `scripts/weekly_research.py`:
   - benchmarks لكل سوق
   - أداء كل استراتيجية
5. فعّل بطاقات الأسواق في الواجهة:
   - Metals card (مفعل)
   - Crypto card (مفعل)
   - إزالة "Coming Soon"
6. حسّن CI و Docker Compose:
   - اختبارات لكل سوق
   - Backtesting لكل سوق
7. أنشئ التقرير الاستشاري النهائي:
   - `reports/AI_Quant_Multi_Market_Advisory_Report.md`
   - حالة المنصة
   - أداء كل استراتيجية/سوق
   - التوصيات

## Outputs
- حسّنات ML وRegime
- حسّنات Weekly Research
- بطاقات مفعلة في الواجهة
- CI/Docker محسّن
- تقرير استشاري نهائي

## Acceptance Criteria
- `pytest tests/ -v` — Exit code 0
- لا Live Trading في أي مكان
- لا bypass للGovernance
- كل استراتيجية تتفوق على Buy & Hold في at least one market
- التقرير الاستشاري النهائي موجود
```

---

# 9. Decision Memo — بوابة توسع الأسواق الجديدة

قبل كتابة أي كود لسوق جديد، يجب إكمال هذا الـDecision Memo وتوثيقه:

```markdown
# Decision Memo: [Market Name]

**Date:** YYYY-MM-DD
**Requested by:** [Team Member]
**Market:** [Metals / Crypto / Egyptian / Other]

## 1. Why this market?
- [reason]

## 2. Data Source
- [provider + URL]

## 3. Trading Calendar
- [hours + timezone]

## 4. Expected Strategies
- [list]

## 5. Benchmark
- [what Buy & Hold looks like for this market]

## 6. Risks
- [market-specific risks]

## 7. Cost Model
- [expected spread, slippage, fees]

## 8. Decision
- [ ] APPROVED — proceed to Wave implementation
- [ ] REJECTED — [reason]
- [ ] DEFERRED — [condition]

## 9. Impact on Code
- [files to change]
```

**يُحفظ في:** `reports/decision_memo_<market>.md`
**يُرسل إلى:** `reports/continuous_research_log.md` كـ entry

---

# 10. مسار التنفيذ المقترح (Recommended Execution Path)

```text
Wave 0 (التعليم)
    │
    ├── بناء المعرفة
    ├── مصطلحات مشتركة
    ├── دروس لكل سوق
    ├── entries في سجل البحوث
    └── بطاقات في الواجهة
    │
    ▼
Wave 1 (طبقة البيانات)
    │
    ├── MetalsProvider + CryptoProvider
    ├── DataProviderRegistry
    ├── تقويمات مختلفة
    ├── فحص جودة لكل سوق
    └── اختبارات جديدة
    │
    ▼
Wave 2 (حزمة الاستراتيجيات)
    │
    ├── StrategyRegistry
    ├── 6 استراتيجيات جديدة
    ├── Long + Short لكل سوق
    ├── اختبارات لكل استراتيجية
    └── التكامل مع TradingPipeline
    │
    ▼
Wave 3 (الاختبار والتحقق)
    │
    ├── Backtesting لكل استراتيجية/سوق
    ├── Paper Trading لكل سوق
    ├── مقارنة مع Buy & Hold
    ├── تكاليف حقيقية
    └── Audit Trail
    │
    ▼
Wave 4 (نشر جميع الأدوات)
    │
    ├── ML لكل سوق
    ├── Regime Detection
    ├── Weekly Research
    ├── تفعيل الواجهة
    ├── CI/Docker
    └── التقرير الاستشاري النهائي
```

**ممنوع التخطي.** كل موج يبني على سابقه.

---

# 11. Final Engineering Directive

قبل كتابة أي Feature جديدة في هذا التوسع، اسألوا:

> هل هذه الإضافة تزيد قدرة المنصة على اتخاذ قرارات تداول أكثر موثوقية في أسواق جديدة، أو تقلل المخاطر، أو تحسن جودة البيانات، أو تحسن التحقق التجريبي، أو تجعل التنفيذ أكثر أمانًا؟

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

ثم ابدؤوا التنفيذ — ابدأ بالدروس أولاً.

---

## References داخل المشروع

- `AI_Quant_Trading_Platform_Master_Development_Prompt.md` — الوثيقة الأساسية
- `docs/professional_development_standard.md` — المعيار المهني
- `reports/continuous_research_log.md` — سجل البحوث
- `pyrobot/strategies/base.py` — BaseStrategy / MultiSymbolStrategy
- `pyrobot/strategies/us_trend.py` — الاستراتيجية الحالية
- `pyrobot/runtime/pipeline.py` — TradingPipeline
- `pyrobot/data/quality.py` — DataQualityEngine
- `pyrobot/ai/training.py` — ML Training Pipeline
- `pyrobot/backtesting/cost_model.py` — ExecutionCostModel
- `us_strategy_backtest.py` — نمط Backtest
- `us_paper_session.py` — نمط Paper Session
- `tests/test_us_trend_strategy.py` — نمط الاختبار
- `scripts/weekly_research.py` — Weekly Research
- `pyrobot/console/static/index.html` — واجهة المستخدم

**End of Multi-Market Wave Directive**
