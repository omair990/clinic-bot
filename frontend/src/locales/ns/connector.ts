// Connector editor: appointment backend selection + per-backend config fields.
// Visible copy only — config keys, type values and logic are unchanged.
// Terms follow the glossary.
export default {
  en: {
    // MapEditor
    keyHead: "Key",
    valueHead: "Value",
    add: "Add",
    // Backend types
    typeNative: "Native (built-in calendar)",
    typeGoogleCalendar: "Google Calendar",
    typeCliniko: "Cliniko",
    typeCustomErp: "Custom ERP",
    typeFhir: "FHIR",
    // Page
    title: "Connector · {name}",
    back: "Back",
    appointmentBackend: "Appointment backend",
    nativeNote:
      "Appointments are stored in this app's own database — no external backend to configure.",
    // Cliniko
    apiKey: "API key",
    businessId: "Business ID",
    userAgent: "User agent",
    practitioners: "Practitioners (doctor → id)",
    appointmentTypes: "Appointment types (service → id)",
    doctor: "Doctor",
    practitionerId: "Practitioner id",
    service: "Service",
    typeId: "Type id",
    // Google Calendar
    refreshToken: "Refresh token",
    timezone: "Timezone",
    defaultCalendar: "Default calendar",
    calendars: "Calendars (doctor → calendarId)",
    calendarId: "Calendar id",
    // Custom ERP / FHIR
    baseUrl: "Base URL",
    bookingStatus: "Booking status",
    bookingStatusPlaceholder: "booked",
    authType: "Auth type",
    authNone: "None",
    authBearer: "Bearer token",
    authHeader: "Custom header",
    authClientCredentials: "Client credentials",
    token: "Token",
    headerName: "Header name",
    headerValue: "Header value",
    tokenUrl: "Token URL",
    clientId: "Client ID",
    clientSecret: "Client secret",
    scope: "Scope",
    schedules: "Schedules (doctor → id)",
    scheduleId: "Schedule id",
    // Secrets
    webhookSecret: "Webhook secret (optional)",
    secretSetPlaceholder: "•••• set — blank keeps",
    secretsSet: "Secrets set (blank keeps): ",
    // Actions
    saveConnector: "Save connector",
    testConnection: "Test connection",
    // Toasts
    connectionOk: "Connection OK",
    testFailed: "Test failed: {detail}",
    connectorSaved: "Connector saved",
    failed: "Failed",
  },
  ar: {
    // MapEditor
    keyHead: "المفتاح",
    valueHead: "القيمة",
    add: "إضافة",
    // Backend types
    typeNative: "محلي (تقويم مدمج)",
    typeGoogleCalendar: "تقويم Google",
    typeCliniko: "Cliniko",
    typeCustomErp: "نظام ERP مخصّص",
    typeFhir: "FHIR",
    // Page
    title: "الموصل · {name}",
    back: "رجوع",
    appointmentBackend: "نظام المواعيد الخلفي",
    nativeNote:
      "تُخزَّن المواعيد في قاعدة بيانات هذا التطبيق نفسه — لا يوجد نظام خلفي خارجي لإعداده.",
    // Cliniko
    apiKey: "مفتاح API",
    businessId: "معرّف النشاط التجاري",
    userAgent: "وكيل المستخدم",
    practitioners: "الممارسون (طبيب → معرّف)",
    appointmentTypes: "أنواع المواعيد (خدمة → معرّف)",
    doctor: "الطبيب",
    practitionerId: "معرّف الممارس",
    service: "الخدمة",
    typeId: "معرّف النوع",
    // Google Calendar
    refreshToken: "رمز التحديث",
    timezone: "المنطقة الزمنية",
    defaultCalendar: "التقويم الافتراضي",
    calendars: "التقاويم (طبيب → معرّف التقويم)",
    calendarId: "معرّف التقويم",
    // Custom ERP / FHIR
    baseUrl: "الرابط الأساسي",
    bookingStatus: "حالة الحجز",
    bookingStatusPlaceholder: "booked",
    authType: "نوع المصادقة",
    authNone: "لا شيء",
    authBearer: "رمز Bearer",
    authHeader: "ترويسة مخصّصة",
    authClientCredentials: "بيانات اعتماد العميل",
    token: "الرمز",
    headerName: "اسم الترويسة",
    headerValue: "قيمة الترويسة",
    tokenUrl: "رابط الرمز",
    clientId: "معرّف العميل",
    clientSecret: "سرّ العميل",
    scope: "النطاق",
    schedules: "الجداول (طبيب → معرّف)",
    scheduleId: "معرّف الجدول",
    // Secrets
    webhookSecret: "سرّ الويب هوك (اختياري)",
    secretSetPlaceholder: "•••• محدّد — اتركه فارغًا للإبقاء",
    secretsSet: "الأسرار المحدّدة (اتركها فارغة للإبقاء): ",
    // Actions
    saveConnector: "حفظ الموصل",
    testConnection: "اختبار الاتصال",
    // Toasts
    connectionOk: "الاتصال سليم",
    testFailed: "فشل الاختبار: {detail}",
    connectorSaved: "تم حفظ الموصل",
    failed: "فشل",
  },
};
