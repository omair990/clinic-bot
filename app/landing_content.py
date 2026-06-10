"""Landing-page content — the single source of truth for every string on /landing.

The marketing page (app/static/landing.html) renders entirely from this content: the
`/landing` route injects `merged(DEFAULTS, overrides)` as `window.__LANDING__`, so the
page is fully bilingual (en/ar) and the super-admin CMS can edit any string without a
redeploy. Overrides are stored as one JSON blob in app_settings under LANDING_SETTING_KEY.

`DEFAULTS`  — { key: {"en": ..., "ar": ...} } for every editable string (and a few meta keys).
`SECTIONS`  — ordered groups of fields (with human labels) that drive the CMS editor UI.

Keep DEFAULTS and SECTIONS in step: every field key listed in SECTIONS must exist in DEFAULTS.
"""
import copy
import json
import logging

log = logging.getLogger(__name__)

LANDING_SETTING_KEY = "LANDING_CONTENT"

# --- Canonical default copy (English + Arabic) ------------------------------------------------
DEFAULTS: dict[str, dict] = {
    # meta (not shown as normal fields, but editable)
    "_title": {"en": "Clinic AI — The WhatsApp AI Receptionist for Clinics | Booking, No-Show Recovery & Insights",
               "ar": "Clinic AI — موظف الاستقبال الذكي للعيادات على واتساب | حجز المواعيد واستعادة الفائتة ورؤى ذكية"},
    "_desc": {"en": "Clinic AI is a WhatsApp AI agent that books, reschedules and cancels appointments end-to-end, recovers no-shows automatically, and replies in 40+ languages.",
              "ar": "Clinic AI مساعد ذكي على واتساب يحجز المواعيد ويعيد جدولتها ويلغيها من البداية للنهاية، ويستعيد المواعيد الفائتة تلقائياً، ويرد بأكثر من 40 لغة."},

    # nav
    "nav_features": {"en": "Features", "ar": "المميزات"},
    "nav_how": {"en": "How it works", "ar": "كيف يعمل"},
    "nav_langs": {"en": "Languages", "ar": "اللغات"},
    "nav_pricing": {"en": "Pricing", "ar": "الأسعار"},
    "nav_faq": {"en": "FAQ", "ar": "الأسئلة الشائعة"},
    "nav_signin": {"en": "Sign in", "ar": "تسجيل الدخول"},
    "nav_demo": {"en": "Book a demo", "ar": "احجز عرضاً توضيحياً"},

    # hero
    "hero_eyebrow": {"en": "Live on WhatsApp · 40+ languages", "ar": "مباشر على واتساب · أكثر من 40 لغة"},
    "hero_h1": {"en": 'The AI receptionist that <span class="grad">books patients while you sleep</span>',
                "ar": 'موظف استقبال ذكي <span class="grad">يحجز المواعيد بينما تنام</span>'},
    "hero_lead": {"en": "Clinic AI talks to your patients on WhatsApp — typed or voice — checks live availability, and books, reschedules or cancels appointments end-to-end. It recovers no-shows automatically and replies in every patient's own language.",
                  "ar": "يتحدث Clinic AI إلى مرضاك على واتساب — كتابةً أو صوتاً — يتحقق من المواعيد المتاحة فوراً، ويحجز ويعيد الجدولة ويلغي المواعيد من البداية للنهاية. يستعيد المواعيد الفائتة تلقائياً ويرد على كل مريض بلغته."},
    "hero_cta1": {"en": "Start free pilot", "ar": "ابدأ تجربة مجانية"},
    "hero_cta2": {"en": "See how it works", "ar": "شاهد كيف يعمل"},
    "hero_note": {"en": "Trusted by modern clinics · No app for patients to install",
                  "ar": "موثوق من العيادات الحديثة · لا حاجة لتطبيق على المرضى"},
    "badge_booked": {"en": "🗓️ Appointment booked", "ar": "🗓️ تم حجز الموعد"},
    "badge_lang": {"en": "🌐 Auto-detected: Arabic", "ar": "🌐 اللغة المكتشفة: العربية"},

    # stats (numbers + captions)
    "stat1_num": {"en": "40+", "ar": "40+"},
    "stat1": {"en": "Languages, replied in the patient's own script", "ar": "لغة، بالرد بنفس كتابة المريض"},
    "stat2_num": {"en": "24/7", "ar": "24/7"},
    "stat2": {"en": "Always-on booking, even after hours", "ar": "حجز دائم، حتى بعد ساعات العمل"},
    "stat3_num": {"en": "100%", "ar": "100%"},
    "stat3": {"en": "End-to-end booking with zero staff touch", "ar": "حجز كامل دون تدخل الموظفين"},
    "stat4_num": {"en": "<3s", "ar": "<3s"},
    "stat4": {"en": "Average reply time on WhatsApp", "ar": "متوسط زمن الرد على واتساب"},

    # features
    "feat_eyebrow": {"en": "Everything your front desk does — automated", "ar": "كل ما يفعله مكتب الاستقبال — آلياً"},
    "feat_h2": {"en": "One assistant. The whole patient journey.", "ar": "مساعد واحد. رحلة المريض كاملة."},
    "feat_lead": {"en": "From the first “hello” to the follow-up after a missed visit, Clinic AI handles it inside WhatsApp — backed by your real schedule and data.",
                  "ar": "من أول «مرحباً» إلى المتابعة بعد موعد فائت، يتولى Clinic AI كل ذلك داخل واتساب — مدعوماً بجدولك وبياناتك الحقيقية."},
    "f1_t": {"en": "Conversational booking", "ar": "الحجز عبر المحادثة"},
    "f1_d": {"en": "Understands free-text and voice notes, checks live doctor availability, and books, reschedules or cancels — no menus, no forms.",
             "ar": "يفهم النصوص الحرة والرسائل الصوتية، ويتحقق من توفر الأطباء مباشرةً، ويحجز ويعيد الجدولة ويلغي — دون قوائم أو نماذج."},
    "f2_t": {"en": "Automatic no-show recovery", "ar": "استعادة المواعيد الفائتة تلقائياً"},
    "f2_d": {"en": "Detects missed visits and reaches out to reschedule, request a call or cancel — then follows up a day later and logs why they missed.",
             "ar": "يكتشف المواعيد الفائتة ويتواصل لإعادة الجدولة أو طلب اتصال أو الإلغاء — ثم يتابع بعد يوم ويسجّل سبب التغيّب."},
    "f3_t": {"en": "No-show risk prediction", "ar": "التنبؤ بخطر التغيّب"},
    "f3_d": {"en": "Scores every upcoming appointment from patient history and sends high-risk patients an extra reminder before they ghost.",
             "ar": "يقيّم كل موعد قادم بناءً على سجل المريض ويرسل تذكيراً إضافياً للأكثر عرضةً للتغيّب قبل أن يختفوا."},
    "f4_t": {"en": "Speaks every patient's language", "ar": "يتحدث لغة كل مريض"},
    "f4_d": {"en": "Auto-detects and replies in 40+ languages and scripts — Arabic, English, Urdu, Hindi, Spanish and more — matching the patient exactly.",
             "ar": "يكتشف لغة المريض ويرد بنفس اللغة والكتابة — أكثر من 40 لغة تشمل العربية والإنجليزية والأردية والهندية والإسبانية وغيرها."},
    "f5_t": {"en": "Voice notes, understood", "ar": "رسائل صوتية مفهومة"},
    "f5_d": {"en": "Patients can send voice messages — transcribed accurately through a resilient fallback chain — and even get spoken replies back.",
             "ar": "يمكن للمرضى إرسال رسائل صوتية — تُحوَّل إلى نص بدقة عبر سلسلة احتياطية موثوقة — بل ويردّ صوتياً أيضاً."},
    "f6_t": {"en": "AI business insights", "ar": "رؤى عمل ذكية"},
    "f6_d": {"en": "Daily and weekly digests on WhatsApp: bookings, conversion, no-shows, peak hours, top doctors and patient sentiment — with what to do next.",
             "ar": "ملخصات يومية وأسبوعية على واتساب: الحجوزات، نسبة التحويل، المواعيد الفائتة، ساعات الذروة، أفضل الأطباء ومشاعر المرضى — مع توصيات للخطوة التالية."},
    "f7_t": {"en": "Human escalation, instantly", "ar": "تحويل فوري لموظف بشري"},
    "f7_d": {"en": "Emergencies and out-of-scope requests hand off to your staff on WhatsApp in real time — the AI knows its limits.",
             "ar": "الحالات الطارئة والطلبات خارج النطاق تُحوَّل إلى فريقك على واتساب فوراً — المساعد يعرف حدوده."},
    "f8_t": {"en": "Multi-branch routing", "ar": "توجيه متعدد الفروع"},
    "f8_d": {"en": "Run several locations from one number — Clinic AI steers each patient to the right branch based on the area they mention.",
             "ar": "أدِر عدة فروع من رقم واحد — يوجّه Clinic AI كل مريض إلى الفرع المناسب حسب المنطقة المذكورة."},
    "f9_t": {"en": "Plugs into your systems", "ar": "يتكامل مع أنظمتك"},
    "f9_d": {"en": "Connect Cliniko, Google Calendar, FHIR-based HIS or a custom ERP — Clinic AI books where your appointments truly live.",
             "ar": "اربط Cliniko أو Google Calendar أو أنظمة HIS المتوافقة مع FHIR أو نظام ERP مخصص — يحجز Clinic AI حيث توجد مواعيدك فعلاً."},

    # how it works
    "how_eyebrow": {"en": "Live in days, not months", "ar": "جاهز خلال أيام، لا أشهر"},
    "how_h2": {"en": "Three steps to an automated front desk", "ar": "ثلاث خطوات لمكتب استقبال آلي"},
    "s1_t": {"en": "Connect your WhatsApp", "ar": "اربط واتساب"},
    "s1_d": {"en": "Link your existing WhatsApp Business number and import your services, doctors and schedule. No new app for patients.",
             "ar": "اربط رقم واتساب للأعمال الحالي واستورد خدماتك وأطباءك وجدولك. لا تطبيق جديد على المرضى."},
    "s2_t": {"en": "Train on your clinic", "ar": "درّبه على عيادتك"},
    "s2_d": {"en": "We load your pricing, policies, branches and booking rules so every answer is grounded in your real data.",
             "ar": "نحمّل أسعارك وسياساتك وفروعك وقواعد الحجز ليكون كل رد مبنياً على بياناتك الحقيقية."},
    "s3_t": {"en": "Go live & watch it work", "ar": "انطلق وراقبه يعمل"},
    "s3_d": {"en": "Patients book, reschedule and get reminders automatically. Your team watches the live dashboard and steps in only when needed.",
             "ar": "يحجز المرضى ويعيدون الجدولة ويتلقون التذكيرات تلقائياً. يراقب فريقك اللوحة المباشرة ويتدخل عند الحاجة فقط."},

    # languages
    "lang_eyebrow": {"en": "No language left behind", "ar": "لا لغة مهملة"},
    "lang_h2": {"en": "Every patient, in their own words", "ar": "كل مريض، بكلماته هو"},
    "lang_lead": {"en": "Clinic AI mirrors each patient's language and script automatically — even in voice notes.",
                  "ar": "يحاكي Clinic AI لغة كل مريض وكتابته تلقائياً — حتى في الرسائل الصوتية."},

    # pricing — single "Custom" plan
    "price_eyebrow": {"en": "Simple, transparent pricing", "ar": "أسعار بسيطة وشفافة"},
    "price_h2": {"en": "One plan, tailored to your clinic", "ar": "باقة واحدة مصمّمة لعيادتك"},
    "price_lead": {"en": "Pay for what you need. Tell us about your clinic and we'll put together a plan that fits.",
                   "ar": "ادفع مقابل ما تحتاجه. أخبرنا عن عيادتك وسنُعد لك باقة تناسبك."},
    "plan_badge": {"en": "Tailored to you", "ar": "مصمّمة لك"},
    "plan_name": {"en": "Custom", "ar": "مخصّصة"},
    "plan_price": {"en": "Let's talk", "ar": "لنتحدث"},
    "plan_desc": {"en": "Everything Clinic AI does, scoped and priced around your clinic — from a single practice to a multi-branch group.",
                  "ar": "كل ما يقدمه Clinic AI، مُصمّم ومُسعّر حسب عيادتك — من عيادة واحدة إلى مجموعة متعددة الفروع."},
    "plan_l1": {"en": "Conversational booking on WhatsApp", "ar": "الحجز عبر المحادثة على واتساب"},
    "plan_l2": {"en": "40+ languages & voice notes", "ar": "أكثر من 40 لغة ورسائل صوتية"},
    "plan_l3": {"en": "Automatic no-show recovery & risk prediction", "ar": "استعادة المواعيد الفائتة تلقائياً والتنبؤ بالتغيّب"},
    "plan_l4": {"en": "Daily & weekly AI insight digests", "ar": "ملخصات رؤى يومية وأسبوعية بالذكاء الاصطناعي"},
    "plan_l5": {"en": "Multi-branch, multi-tenant & ERP / Calendar / HIS integrations", "ar": "متعدد الفروع والمستأجرين وتكامل ERP / التقويم / HIS"},
    "plan_l6": {"en": "Unlimited conversations & dedicated support", "ar": "محادثات غير محدودة ودعم مخصص"},
    "plan_btn": {"en": "Request a demo", "ar": "اطلب عرضاً توضيحياً"},

    # FAQ
    "faq_eyebrow": {"en": "Good to know", "ar": "معلومات مفيدة"},
    "faq_h2": {"en": "Frequently asked questions", "ar": "الأسئلة الشائعة"},
    "q1": {"en": "Does it work inside WhatsApp?", "ar": "هل يعمل داخل واتساب؟"},
    "a1": {"en": "Yes. Patients simply message your existing WhatsApp Business number — there's nothing for them to install. Clinic AI handles the whole conversation, and your staff watch it live from the dashboard.",
           "ar": "نعم. يراسل المرضى ببساطة رقم واتساب للأعمال الحالي — لا شيء يحتاجون لتثبيته. يتولى Clinic AI المحادثة كاملةً، ويراقبها فريقك مباشرةً من اللوحة."},
    "q2": {"en": "Which languages are supported?", "ar": "ما اللغات المدعومة؟"},
    "a2": {"en": "Over 40, including Arabic, English, Urdu, Hindi, Spanish and French. The assistant detects the patient's language and replies in the same language and script — even responding to voice notes.",
           "ar": "أكثر من 40 لغة، تشمل العربية والإنجليزية والأردية والهندية والإسبانية والفرنسية. يكتشف المساعد لغة المريض ويرد بنفس اللغة والكتابة — حتى على الرسائل الصوتية."},
    "q3": {"en": "Can it really book appointments on its own?", "ar": "هل يحجز المواعيد بنفسه فعلاً؟"},
    "a3": {"en": "Yes. It checks live doctor availability and books, reschedules or cancels end-to-end. Anything sensitive — emergencies or out-of-scope requests — is escalated to a human instantly.",
           "ar": "نعم. يتحقق من توفر الأطباء مباشرةً ويحجز ويعيد الجدولة ويلغي من البداية للنهاية. وأي أمر حساس — حالة طارئة أو خارج النطاق — يُحوَّل إلى موظف بشري فوراً."},
    "q4": {"en": "How does no-show recovery work?", "ar": "كيف تعمل استعادة المواعيد الفائتة؟"},
    "a4": {"en": "When a confirmed patient never checks in, Clinic AI messages them to reschedule, request a call, or cancel, then nudges again a day later — capturing the reason they missed so you can act on it.",
           "ar": "عندما لا يحضر مريض مؤكد، يراسله Clinic AI لإعادة الجدولة أو طلب اتصال أو الإلغاء، ثم يذكّره مجدداً بعد يوم — مع تسجيل سبب التغيّب لتتمكن من التصرف."},
    "q5": {"en": "Does it connect to our existing system?", "ar": "هل يتكامل مع نظامنا الحالي؟"},
    "a5": {"en": "It can. Clinic AI runs natively or plugs into Cliniko, Google Calendar, FHIR-based hospital systems, or a custom ERP — so appointments live where you already manage them.",
           "ar": "نعم. يعمل Clinic AI أصلياً أو يتكامل مع Cliniko أو Google Calendar أو أنظمة المستشفيات المتوافقة مع FHIR أو نظام ERP مخصص — لتبقى المواعيد حيث تديرها بالفعل."},

    # CTA band
    "cta_eyebrow": {"en": "Ready when you are", "ar": "جاهزون متى استعددت"},
    "cta_h2": {"en": "Turn every WhatsApp message into a booked appointment", "ar": "حوّل كل رسالة واتساب إلى موعد محجوز"},
    "cta_lead": {"en": "Launch a free pilot and see your front desk run itself — in your patients' language, around the clock.",
                 "ar": "أطلق تجربة مجانية وشاهد مكتب استقبالك يدير نفسه — بلغة مرضاك، على مدار الساعة."},
    "cta_btn1": {"en": "Request a demo", "ar": "اطلب عرضاً توضيحياً"},
    "cta_btn2": {"en": "Explore features", "ar": "استكشف المميزات"},

    # footer
    "foot_tag": {"en": "The WhatsApp AI receptionist for clinics.", "ar": "موظف الاستقبال الذكي للعيادات على واتساب."},

    # booking request form (modal)
    "form_title": {"en": "Request a demo", "ar": "اطلب عرضاً توضيحياً"},
    "form_sub": {"en": "Tell us about your clinic and we'll reach out on WhatsApp.", "ar": "أخبرنا عن عيادتك وسنتواصل معك على واتساب."},
    "form_name": {"en": "Your name", "ar": "اسمك"},
    "form_phone": {"en": "WhatsApp number", "ar": "رقم واتساب"},
    "form_clinic": {"en": "Clinic name", "ar": "اسم العيادة"},
    "form_message": {"en": "Message (optional)", "ar": "رسالة (اختياري)"},
    "form_submit": {"en": "Submit request", "ar": "إرسال الطلب"},
    "form_sending": {"en": "Sending…", "ar": "جارٍ الإرسال…"},
    "form_success": {"en": "Thank you! We'll be in touch on WhatsApp shortly.", "ar": "شكراً لك! سنتواصل معك على واتساب قريباً."},
    "form_error": {"en": "Something went wrong. Please try again.", "ar": "حدث خطأ ما. يرجى المحاولة مرة أخرى."},
    "form_required": {"en": "Please enter your name and WhatsApp number.", "ar": "يرجى إدخال اسمك ورقم واتساب."},
    "form_close": {"en": "Close", "ar": "إغلاق"},
}

# --- CMS editor schema: ordered sections of fields with friendly labels ----------------------
# `multiline` hints the CMS to render a textarea; `html` flags fields that may contain markup.
SECTIONS: list[dict] = [
    {"key": "meta", "title": "SEO / Meta", "fields": [
        {"key": "_title", "label": "Browser title", "multiline": True},
        {"key": "_desc", "label": "Meta description", "multiline": True},
    ]},
    {"key": "nav", "title": "Navigation", "fields": [
        {"key": "nav_features", "label": "Features"}, {"key": "nav_how", "label": "How it works"},
        {"key": "nav_langs", "label": "Languages"}, {"key": "nav_pricing", "label": "Pricing"},
        {"key": "nav_faq", "label": "FAQ"}, {"key": "nav_signin", "label": "Sign in"},
        {"key": "nav_demo", "label": "Book a demo button"},
    ]},
    {"key": "hero", "title": "Hero", "fields": [
        {"key": "hero_eyebrow", "label": "Eyebrow"},
        {"key": "hero_h1", "label": "Headline (HTML)", "multiline": True, "html": True},
        {"key": "hero_lead", "label": "Subtext", "multiline": True},
        {"key": "hero_cta1", "label": "Primary button"}, {"key": "hero_cta2", "label": "Secondary button"},
        {"key": "hero_note", "label": "Trust note"},
        {"key": "badge_booked", "label": "Phone badge — booked"}, {"key": "badge_lang", "label": "Phone badge — language"},
    ]},
    {"key": "stats", "title": "Stats", "fields": [
        {"key": "stat1_num", "label": "Stat 1 — number"}, {"key": "stat1", "label": "Stat 1 — caption"},
        {"key": "stat2_num", "label": "Stat 2 — number"}, {"key": "stat2", "label": "Stat 2 — caption"},
        {"key": "stat3_num", "label": "Stat 3 — number"}, {"key": "stat3", "label": "Stat 3 — caption"},
        {"key": "stat4_num", "label": "Stat 4 — number"}, {"key": "stat4", "label": "Stat 4 — caption"},
    ]},
    {"key": "features", "title": "Features", "fields": [
        {"key": "feat_eyebrow", "label": "Eyebrow"}, {"key": "feat_h2", "label": "Heading"},
        {"key": "feat_lead", "label": "Subtext", "multiline": True},
        {"key": "f1_t", "label": "Feature 1 — title"}, {"key": "f1_d", "label": "Feature 1 — text", "multiline": True},
        {"key": "f2_t", "label": "Feature 2 — title"}, {"key": "f2_d", "label": "Feature 2 — text", "multiline": True},
        {"key": "f3_t", "label": "Feature 3 — title"}, {"key": "f3_d", "label": "Feature 3 — text", "multiline": True},
        {"key": "f4_t", "label": "Feature 4 — title"}, {"key": "f4_d", "label": "Feature 4 — text", "multiline": True},
        {"key": "f5_t", "label": "Feature 5 — title"}, {"key": "f5_d", "label": "Feature 5 — text", "multiline": True},
        {"key": "f6_t", "label": "Feature 6 — title"}, {"key": "f6_d", "label": "Feature 6 — text", "multiline": True},
        {"key": "f7_t", "label": "Feature 7 — title"}, {"key": "f7_d", "label": "Feature 7 — text", "multiline": True},
        {"key": "f8_t", "label": "Feature 8 — title"}, {"key": "f8_d", "label": "Feature 8 — text", "multiline": True},
        {"key": "f9_t", "label": "Feature 9 — title"}, {"key": "f9_d", "label": "Feature 9 — text", "multiline": True},
    ]},
    {"key": "how", "title": "How it works", "fields": [
        {"key": "how_eyebrow", "label": "Eyebrow"}, {"key": "how_h2", "label": "Heading"},
        {"key": "s1_t", "label": "Step 1 — title"}, {"key": "s1_d", "label": "Step 1 — text", "multiline": True},
        {"key": "s2_t", "label": "Step 2 — title"}, {"key": "s2_d", "label": "Step 2 — text", "multiline": True},
        {"key": "s3_t", "label": "Step 3 — title"}, {"key": "s3_d", "label": "Step 3 — text", "multiline": True},
    ]},
    {"key": "languages", "title": "Languages section", "fields": [
        {"key": "lang_eyebrow", "label": "Eyebrow"}, {"key": "lang_h2", "label": "Heading"},
        {"key": "lang_lead", "label": "Subtext", "multiline": True},
    ]},
    {"key": "pricing", "title": "Pricing (single Custom plan)", "fields": [
        {"key": "price_eyebrow", "label": "Eyebrow"}, {"key": "price_h2", "label": "Heading"},
        {"key": "price_lead", "label": "Subtext", "multiline": True},
        {"key": "plan_badge", "label": "Plan badge"}, {"key": "plan_name", "label": "Plan name"},
        {"key": "plan_price", "label": "Plan price"}, {"key": "plan_desc", "label": "Plan description", "multiline": True},
        {"key": "plan_l1", "label": "Bullet 1"}, {"key": "plan_l2", "label": "Bullet 2"},
        {"key": "plan_l3", "label": "Bullet 3"}, {"key": "plan_l4", "label": "Bullet 4"},
        {"key": "plan_l5", "label": "Bullet 5"}, {"key": "plan_l6", "label": "Bullet 6"},
        {"key": "plan_btn", "label": "Plan button"},
    ]},
    {"key": "faq", "title": "FAQ", "fields": [
        {"key": "faq_eyebrow", "label": "Eyebrow"}, {"key": "faq_h2", "label": "Heading"},
        {"key": "q1", "label": "Q1"}, {"key": "a1", "label": "A1", "multiline": True},
        {"key": "q2", "label": "Q2"}, {"key": "a2", "label": "A2", "multiline": True},
        {"key": "q3", "label": "Q3"}, {"key": "a3", "label": "A3", "multiline": True},
        {"key": "q4", "label": "Q4"}, {"key": "a4", "label": "A4", "multiline": True},
        {"key": "q5", "label": "Q5"}, {"key": "a5", "label": "A5", "multiline": True},
    ]},
    {"key": "cta", "title": "Call to action", "fields": [
        {"key": "cta_eyebrow", "label": "Eyebrow"}, {"key": "cta_h2", "label": "Heading", "multiline": True},
        {"key": "cta_lead", "label": "Subtext", "multiline": True},
        {"key": "cta_btn1", "label": "Primary button"}, {"key": "cta_btn2", "label": "Secondary button"},
    ]},
    {"key": "footer", "title": "Footer", "fields": [
        {"key": "foot_tag", "label": "Tagline"},
    ]},
    {"key": "form", "title": "Request form", "fields": [
        {"key": "form_title", "label": "Title"}, {"key": "form_sub", "label": "Subtitle", "multiline": True},
        {"key": "form_name", "label": "Name label"}, {"key": "form_phone", "label": "WhatsApp label"},
        {"key": "form_clinic", "label": "Clinic label"}, {"key": "form_message", "label": "Message label"},
        {"key": "form_submit", "label": "Submit button"}, {"key": "form_sending", "label": "Sending state"},
        {"key": "form_success", "label": "Success message", "multiline": True},
        {"key": "form_error", "label": "Error message", "multiline": True},
        {"key": "form_required", "label": "Validation message", "multiline": True},
        {"key": "form_close", "label": "Close button"},
    ]},
]


def _load_overrides() -> dict:
    """Saved CMS overrides ({key: {en?, ar?}}) from app_settings, or {} on any failure."""
    try:
        from app import settings as settings_mod
        raw = settings_mod.get(LANDING_SETTING_KEY)
        if not raw:
            return {}
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001 — content must never break the page
        log.warning("failed to load landing overrides", exc_info=True)
        return {}


def merged_content() -> dict:
    """Full content (defaults with saved overrides applied), as { key: {en, ar} }."""
    content = copy.deepcopy(DEFAULTS)
    for key, val in _load_overrides().items():
        if key in content and isinstance(val, dict):
            for lang in ("en", "ar"):
                if val.get(lang):
                    content[key][lang] = val[lang]
    return content


def save_overrides(values: dict) -> None:
    """Persist only the values that differ from DEFAULTS (so re-defaulting is automatic)."""
    from app import settings as settings_mod
    clean: dict[str, dict] = {}
    for key, val in (values or {}).items():
        if key not in DEFAULTS or not isinstance(val, dict):
            continue
        entry = {}
        for lang in ("en", "ar"):
            v = (val.get(lang) or "").strip()
            if v and v != DEFAULTS[key].get(lang):
                entry[lang] = v
        if entry:
            clean[key] = entry
    settings_mod.set_value(LANDING_SETTING_KEY, json.dumps(clean, ensure_ascii=False))


def cms_schema() -> dict:
    """Sections + every field's current (merged) en/ar value — drives the CMS editor."""
    content = merged_content()
    sections = []
    for sec in SECTIONS:
        fields = []
        for f in sec["fields"]:
            cur = content.get(f["key"], {})
            fields.append({**f, "en": cur.get("en", ""), "ar": cur.get("ar", "")})
        sections.append({"key": sec["key"], "title": sec["title"], "fields": fields})
    return {"sections": sections}
