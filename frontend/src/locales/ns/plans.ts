// Plans & usage page (super-admin): clinics, plans and monthly usage. Visible copy only —
// status values, API paths, query keys and apiPost body keys keep their logic.
// Terms follow the glossary.
export default {
  en: {
    title: "Plans & usage",
    subtitle: "Clinics, plans and monthly usage",
    addClinic: "Add clinic",
    // KPI cards
    kpiClinics: "Clinics",
    kpiActive: "Active",
    kpiSuspendedExpired: "Suspended / expired",
    kpiPackages: "Packages",
    // Section headers
    sectionClinics: "Clinics",
    sectionPackages: "Packages",
    newPackage: "New package",
    // Clinic-card status options
    statusActive: "active",
    statusSuspended: "suspended",
    statusExpired: "expired",
    // UsageBar
    usageText: "Text",
    usageVoice: "Voice",
    usageOff: "off",
    // Clinic-card actions
    editClinic: "Edit clinic",
    connector: "Connector",
    // Package card
    sarPerMo: "SAR / mo",
    trialDays: "Trial · {n}d",
    textPerMo: "{n} text / mo",
    voicePerMo: "{n} voice / mo",
    voiceOff: "Voice off",
    // AddClinicDialog
    addClinicTitle: "Add clinic",
    fieldName: "Name",
    fieldSlug: "Slug (unique)",
    fieldPhoneNumberId: "WhatsApp phone_number_id",
    fieldTimezone: "Timezone",
    fieldWaToken: "WhatsApp token (optional)",
    fieldStaffUsername: "Staff username (optional)",
    fieldStaffPassword: "Staff password (optional)",
    fieldClinicData: "Clinic data JSON (optional)",
    createClinic: "Create clinic",
    createFailed: "Create failed",
    // PackageDialog
    editPackage: "Edit package",
    pkgName: "Name (existing name = edit)",
    pkgTextQuota: "Monthly text quota (blank = unlimited)",
    pkgVoiceEnabled: "Voice enabled",
    pkgVoiceQuota: "Monthly voice quota (blank = unlimited)",
    pkgTrialPlan: "Trial plan",
    pkgTrialDays: "Trial days",
    pkgPrice: "Price (SAR)",
    savePackage: "Save package",
    // Toasts
    planUpdated: "Plan updated",
    statusUpdated: "Status updated",
    packageSaved: "Package saved",
  },
  ar: {
    title: "الباقات والاستخدام",
    subtitle: "العيادات والباقات والاستخدام الشهري",
    addClinic: "إضافة عيادة",
    // KPI cards
    kpiClinics: "العيادات",
    kpiActive: "نشط",
    kpiSuspendedExpired: "موقوف / منتهٍ",
    kpiPackages: "الباقات",
    // Section headers
    sectionClinics: "العيادات",
    sectionPackages: "الباقات",
    newPackage: "باقة جديدة",
    // Clinic-card status options
    statusActive: "نشط",
    statusSuspended: "موقوف",
    statusExpired: "منتهٍ",
    // UsageBar
    usageText: "نصية",
    usageVoice: "صوتية",
    usageOff: "مغلق",
    // Clinic-card actions
    editClinic: "تعديل العيادة",
    connector: "الموصل",
    // Package card
    sarPerMo: "ريال/شهر",
    trialDays: "تجريبية · {n}ي",
    textPerMo: "{n} نصية/شهر",
    voicePerMo: "{n} صوتية/شهر",
    voiceOff: "الصوت مغلق",
    // AddClinicDialog
    addClinicTitle: "إضافة عيادة",
    fieldName: "الاسم",
    fieldSlug: "المعرّف (فريد)",
    fieldPhoneNumberId: "WhatsApp phone_number_id",
    fieldTimezone: "المنطقة الزمنية",
    fieldWaToken: "رمز واتساب (اختياري)",
    fieldStaffUsername: "اسم مستخدم الموظف (اختياري)",
    fieldStaffPassword: "كلمة مرور الموظف (اختياري)",
    fieldClinicData: "بيانات العيادة JSON (اختياري)",
    createClinic: "إنشاء العيادة",
    createFailed: "فشل الإنشاء",
    // PackageDialog
    editPackage: "تعديل الباقة",
    pkgName: "الاسم (اسم موجود = تعديل)",
    pkgTextQuota: "حصة النصوص الشهرية (فارغ = غير محدود)",
    pkgVoiceEnabled: "الصوت مُفعّل",
    pkgVoiceQuota: "حصة الصوت الشهرية (فارغ = غير محدود)",
    pkgTrialPlan: "باقة تجريبية",
    pkgTrialDays: "أيام التجربة",
    pkgPrice: "السعر (ريال)",
    savePackage: "حفظ الباقة",
    // Toasts
    planUpdated: "تم تحديث الباقة",
    statusUpdated: "تم تحديث الحالة",
    packageSaved: "تم حفظ الباقة",
  },
};
