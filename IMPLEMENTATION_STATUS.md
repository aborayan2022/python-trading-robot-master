# حالة تنفيذ خارطة الطريق الاستشارية — 2026-08-23

مرجع القرار: `reports/الرأي_الاستشاري_الصريح_2026-08-22.md`
الحالة الإجمالية: **P0 مكتملة بالكامل + P1 مكتملة بالكامل + العناصر الجوهرية من P2 مكتملة** — 411 اختبارًا تنجح (كانت 276)، ruff نظيف بالكامل، mypy نظيف بالكامل على الحزم المفرَضة.

---

## المرحلة P0 — "اجعلها تتداول بأمان" ✅ مكتملة

| البند | الحالة | الأدلة |
|---|---|---|
| 1. مسار واحد متصل من طرف لطرف | ✅ | `pyrobot/runtime/pipeline.py` — `TradingPipeline`: بيانات → ميزات → إشارة (AI أو Strategy) → مخاطر → تنفيذ → تدقيق → دفتر مخاطر. اختبارات تكامل في `tests/test_runtime.py` (11 اختبارًا) تثبت: إشارة → تعبئة فعلية في الوسيط → موضع حقيقي → أحداث تدقيق كاملة بسلسلة قابلة للتحقق |
| 2. حلقة تشغيل رئيسية | ✅ | `pyrobot/runtime/loop.py` — `TradingLoop`: نبضات قلب، إيقاف رشيق (SIGINT/SIGTERM)، وضع ورقي افتراضي، مصدر بيانات Replay حتمي + قابلية توصيل أي مزود أسعار حي. التشغيل الفعلي: `python -m pyrobot.runtime.loop` |
| 3. إصلاحات الأمان الحرجة | ✅ | اتجاه البيع في `risk/exposure.py` (إغلاق Long لم يعد يُرفض كتعرض Short)، خلق النقد من البيع المكشوف في `paper_broker.py` (دفتر مراكز قصيرة كامل مع تغطية وتحقيق أرباح)، تجاوز الوسيط في `robot.py` (كل الأوامر عبر `broker.place_order`) |
| 4. إلغاء الأوامر | ✅ | `cancel_order` على `BrokerInterface` (abstract) + الأربع adapters + `ExecutionEngine.cancel_order` مع آلة حالات CANCEL_PENDING→CANCELLED وحدث تدقيق ORDER_CANCELLED |
| 5. سجل تدقيق دائم | ✅ | `audit/ledger.py`: تحميل من القرص عند الإقلاع + `AuditIntegrityError` عند العبث + استمرارية المعرفات + أحداث ORDER_FILLED وKILL_SWITCH_TRIGGERED تُسجَّل فعليًا + `verify_file_integrity` |
| 6. صدق البنية | ✅ | حاوية `bot` تشغّل حلقة التداول الحقيقية (`python -m pyrobot.runtime.loop`) بدل استيراد المكتبة والخروج؛ Postgres/Redis/Grafana انتقلت لـ profile مستقل (`--profile full`) لأن لا كود يستهلكها بعد |

## المرحلة P1 — "صدق التقييم" ✅ مكتملة

| البند | الحالة | الأدلة |
|---|---|---|
| تنفيذ الشريط التالي | ✅ | `backtesting/engine.py`: إشارة الشريط t تُنفَّذ عند **فتح** الشريط t+1 — اختبار `test_next_bar_execution` يثبت الدخول عند open وليس close |
| لا نظرة مستقبلية | ✅ | الاستراتيجية ترى نافذة ماضية فقط (صفوف ≤ الشريط الحالي) — اختبار `test_strategy_sees_only_past_rows` |
| ربط نموذج التكاليف | ✅ | `ExecutionCostModel` (الموجود أصلًا والذي كان كودًا ميتًا) أصبح مسار التنفيذ الوحيد: عمولات، انزلاق متطاير، أثر سوق جذري، تعبئة جزئية بحد مشاركة 10% مع إعادة محاولة الكمية المتبقية |
| وقف داخل الشريط + فجوات | ✅ | خروج عند min(open, stop) عند الفجوة، والوقف يُقدَّم على الهدف عند تلامسهما (متحفظ) — اختبارات `test_stop_loss_intrabar_no_gap` و`test_stop_loss_gap_through_open` |
| توحيد المقاييس | ✅ | `BacktestResult` يفوّض إلى `metrics.py`؛ التسنيد أصبح بدلالة `periods_per_year` مشتقة من `bar_type` (دقيقة/ساعة/يوم) بدل 252 الصلبة |
| Walk-forward حقيقي | ✅ | `run_walk_forward()`: إعادة تدريب لكل طية + تجميع out-of-sample واحد + نتيجة عامة (model-agnostic) |
| Monte Carlo صادق | ✅ | `default_rng` بالبذرة (حتمية مختبرة)، إصلاح الاحتساب المزدوج للخسارة الكارثية، Sharpe لكل صفقة دون تجذير 252 المضلل |
| اختبارات سلوكية | ✅ | دخانية القديمة استُبدلت: العمولة تخفض الحصيلة فعليًا، الحجم الصغير ينتج تعبئة جزئية (10 أسهم/شريط)، لا تنفيذ على آخر شريط |

## المرحلة P2 — "ذكاء اصطناعي حقيقي" ◐ العناصر الجوهرية مكتملة

| البند | الحالة | الأدلة |
|---|---|---|
| باني التسميات | ✅ | `ai/labels.py` — `LabelBuilder`: عوائد أمامية متعددة الآفاق، تسميات اتجاهية بعتبة، **Triple-Barrier** (ATR ماضٍ فقط، وقف يسبق الهدف عند التعارض) — قيم محسوبة يدويًا في الاختبارات. حلقة ML أصبحت قابلة للتشغيل من البداية للنهاية |
| تسمية صادقة | ✅ | `GBDTDirectionClassifier` → `LogisticDirectionModel` (مع alias للتوافق + إزالة `max_depth` الميت + معاملات حقيقية: l2_reg, tol, تقارب مبكر مع `n_iter_run`)؛ `LLMContextEngine` → `LexiconSentimentEngine` (اعتراف صريح بأنه عدّاد معجم لا LLM) |
| عتبات ensemble صادقة | ✅ | إزالة الشرطين الميتين (0.55/0.45)؛ عتبة واحدة صريحة `min_probability=0.80` + عتبة خروج `exit_probability` + **إشارات خروج فعلية** (SELL لتصفية Long وBUY_TO_COVER لتغطية Short عبر `position_state`) |
| Registry يحفظ الأوزان | ✅ | `register_model(metadata, model=fitted)` يكتب artifact بصيغة npz آمنة (بلا pickle) + SHA-256 يُتحقق منه عند `load_model` — اختبار عبث فعلي بالملف يرفع `ArtifactIntegrityError` |
| موصولية الانحراف | ✅ | PSI يعمل داخل الحلقة (`MODEL_DRIFT_CHECK` في التدقيق) ويقلّص حجم المراكز عبر `RiskManager.set_model_risk_scale` (1.0 / 0.75 / 0.25 حسب التوصية) |
| تحميل البطل تلقائيًا | ✅ | الـ ensemble يحمّل champion من السجل كسولًا عند غياب نماذج ممررة |
| LightGBM/معايرة احتمالات | ⏳ | الخطوة التالية الطبيعية — البنية جاهزة (واجهة fit/predict، registry بـ artifacts، walk-forward عام) |
| عنصر 2026 المميز (وكلاء LLM / نماذج أساس) | ⏳ | خارج هذه الدفعة — يُنفَّذ بعد استقرار الخط الأساس |

## المرحلة P3 — "تشغيل حقيقي" ⏳ لم تبدأ (كما خطط التقرير: تتطلب 3-6 أشهر ورقي موثق أولاً)

بث websocket، مواءمة مراكز دورية، TWAP، ربط Postgres/Redis/Grafana فعليًا — كلها لاحقة.

---

## إصلاحات إضافية نُفذت من بند "الأخطاء الملموسة" في التقرير

- **البيع يُحتسب زيادة للتعرض Short** → دلالات اتجاه صحيحة مع المراكز الحالية (`exposure.py::check_order(positions=...)`) + اختبارات سلوكية.
- **الحدود الميتة** (`max_correlation_threshold`/`max_volatility_threshold`) → تُفرض فعليًا عند توفير مصفوفة الارتباط/خريطة التقلب.
- **القيم السحرية في التحجيم** → حقلا `RiskLimits.default_stop_distance_pct` و`per_trade_risk_pct` موثقان.
- **الـ PaperBroker**: LIMIT ينتظر عبور السعر (لا تنفيذ شرطي أعمى)، STOP يُطلق عند العبور، عمولات اختيارية، `avg_fill_price` في حالة الأمر (يصلح مصالحة التنفيذ)، دفتر قصيرة كامل.
- **المصالحة تتجاوز آلة الحالات** → `OrderManager.resolve_unknown` بمسارات انتقال قانونية.
- **فحص السياق المخاطر الصفري يمر بفراغ** → fail-closed: رمز بلا سعر = رفض الأمر.
- **قاطع الدائرة**: `cooldown_seconds` صريح + HALF_OPEN يسمح بأمر اختبار واحد (خسارته تُعيد الفتح).
- **`Dict[str, any]`** → `Dict[str, Any]`، وتعقيم معرفات السجل لمسارات الملفات.

## البنية التحتية

- **CI**: ruff نظيف 100% على `pyrobot/`؛ mypy مفروض وصفر أخطاء على الحزم الجديدة/المعاد بناؤها (ai/backtesting/runtime/risk/execution/audit — 31 ملفًا) مع خطوة تقرير غير حاجزة للشجرة الكاملة.
- **Docker**: `docker compose up` يشغّل حلقة تداول ورقية حقيقية (مع `PYROBOT_SIGNAL_SOURCE=example` تتداول فعليًا: إشارات → مخاطر → تعبئات → سلسلة تدقيق سليمة على القرص).
- **دين تقني متبقٍ (موثق بشفافية)**: ~130 خطأ mypy في الوحدات القديمة (robot/trades/portfolio/indicators/stock_frame/adapters الوسطاء) موجودة قبل هذه الخارطة — إصلاحها التدريجي مسار منفصل.

## التحقق النهائي (2026-08-23)

```
pytest tests/            → 411 passed (baseline قبل التنفيذ: 276)
ruff check pyrobot/      → All checks passed
mypy (الحزم المفروضة)    → Success: no issues found in 31 source files
python -m pyrobot.runtime.loop (وضع example، 200 شريط)
  → 200 MARKET_DATA_RECORDED / 5 SIGNAL_GENERATED / 5 RISK_EVALUATED
    / 5 ORDER_SUBMITTED / 5 ORDER_FILLED — verify_file_integrity: True
```

## الأولويات التالية (بالترتيب)

1. خط أساس ML حقيقي: تدريب LogisticDirectionModel عبر `run_walk_forward` على بيانات حقيقية ومقارنته بشراء-واحتجاز (قبل أي مكتبات أثقل).
2. LightGBM + معايرة Isotonic خلف نفس الواجهات.
3. مصدر بيانات حي (Alpaca polling ثم streaming) لتحل محل الـ Replay في الحلقة.
4. سداد دين mypy في الوحدات القديمة حزمةً بحزمة لاستعادة الفحص الكامل الصارم.
5. 3-6 أشهر ورقي موثق قبل أي نقاش عن أموال حقيقية (قاعدة التقرير الملزمة).
