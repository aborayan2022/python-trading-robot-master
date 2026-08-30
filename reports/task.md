# Task List — AI Quant Trading Platform

## 🛡️ Phase 0: سد الثغرات الحرجة (Safety & Risk Gate)
- [x] فحص الكود الحالي في `execution/engine.py`
- [x] جعل `risk_manager` إلزامياً وإلزامية فحص المخاطر قبل أي أمر
- [x] إضافة `RiskDecision` dataclass كنتيجة موثقة لفحص المخاطر
- [x] بناء حساب Realized PnL دقيق ومحاسبة الصفقات والعمولات في `risk/manager.py`
- [x] التحقق من `client_order_id` (UUID4) وإدارة دورة حياة الأوامر وحالة `UNKNOWN`
- [x] تعزيز `KillSwitch` بأسباب التوقف الشاملة (position mismatch, model failure, stale data)
- [x] إنشاء حزمة `pyrobot/audit/` وسجل التدقيق المشفر `AuditLedger` بسلسلة SHA-256
- [x] دمج `AuditLedger` مع `ExecutionEngine` لتسجيل كافة القرارات آلياً
- [x] إصلاح CI/CD (إزالة `continue-on-error` على mypy وتحديث CodeQL إلى v3)
- [x] Docker Production Hardening (تثبيت إصدارات Postgres, Redis, Grafana ومعالجة RDB v12)
- [x] تحديث الاختبارات واجتياز اختبارات الأمان والتدقيق بنسبة 100%

## 📊 Phase 1: منصة البيانات وإدارة الجودة (Data Platform)
- [x] فصل طبقة البيانات عن الوسيط مع `MarketDataProvider`
- [x] بناء `DatasetStore` و `DatasetVersion` لحفظ مجموعات البيانات بتنسيق Parquet مع بصمات SHA-256
- [x] بناء `MarketDataFeed` مع كاشف البيانات القديمة والمتوقفة (`StaleDataError`)
- [x] تفعيل محرك جودة البيانات `DataQualityEngine` وكشف التناقضات والفجوات السعرية
- [x] اختبارات منصة البيانات في `tests/test_data_platform.py`

## ⏱️ Phase 2: محرك الـ Backtesting المؤسسي ونموذج التكاليف
- [x] بناء نموذج التكاليف الواقعي `ExecutionCostModel` (Spread, Slippage, SEC/FINRA fees, Partial fills)
- [x] تفعيل التحقق المستقبلي `WalkForwardValidator` و Purged Cross-Validation
- [x] تفعيل محاكاة الضغط الإحصائي `MonteCarloSimulator`
- [x] حساب المقاييس الكمية المتقدمة (Calmar, Ulcer Index, VaR, CVaR)
- [x] اختبارات Backtesting في `tests/test_backtesting.py` و `tests/test_advanced_backtesting.py`

## 🧠 Phase 3 & 4: الذكاء الاصطناعي والتعلم الآلي (AI/ML Engine)
- [x] بناء سجل وحوكمة النماذج `ModelRegistry` بنظام Champion vs Challenger
- [x] بناء نموذج التوقع الاتجاهي `GBDTDirectionClassifier` مع حساب Feature Importances
- [x] بناء نموذج توقع التذبذب `VolatilityForecaster` لتحديد الحجم الديناميكي
- [x] بناء كاشف أنماط السوق `MarketRegimeDetector` مع إيقاف التداول في نمط الأزمات `CRISIS`
- [x] بناء محرك الإشارات المجمعة `EnsembleSignalEngine` لدمج النماذج ومعايرة الثقة
- [x] بناء كاشف انحراف النماذج والميزات `DriftDetector` بمؤشر PSI
- [x] بناء طبقة الذكاء المساعد وتفسير القرارات `LLMContextEngine`
- [x] اختبارات منظومة الذكاء الاصطناعي في `tests/test_ai_platform.py`

---
**النتيجة الإجمالية:** ✅ **276 / 276 اختبار ناجح بنسبة 100%**



