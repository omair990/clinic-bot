// Manage-clinic (super-admin) edit page. Visible copy only — API paths, query keys and
// apiPost body keys keep their logic. Terms follow the glossary.
export default {
  en: {
    pageTitle: "Manage clinic · {name}",
    connector: "Connector",
    back: "Back",
    // Account & WhatsApp card
    accountWhatsapp: "Account & WhatsApp",
    name: "Name",
    slug: "Slug",
    immutable: "Immutable",
    timezone: "Timezone",
    waPhoneNumberId: "WhatsApp phone_number_id",
    waAccessToken: "WhatsApp access token",
    waTokenSet: "•••• set — blank keeps",
    waTokenNotSet: "not set",
    staffUsername: "Staff username",
    staffPassword: "Staff password",
    blankKeeps: "blank keeps",
    // Clinic data
    clinicData: "Clinic data",
    fixBeforeSaving: "Fix these before saving:",
    saveClinic: "Save clinic",
    // Danger zone
    dangerZone: "Danger zone",
    deleteWarning: "Permanently delete this clinic and all its data. Type the slug {slug} to confirm.",
    confirmSlug: "Confirm slug",
    deleteClinic: "Delete clinic",
    defaultCannotDelete: "The default tenant cannot be deleted.",
    // Toasts
    clinicSaved: "Clinic saved",
    savedWithWarnings: "Saved ({n} warning(s))",
    clinicDeleted: "Clinic deleted",
    saveFailed: "Save failed",
    deleteFailed: "Delete failed",
    fixHighlighted: "Please fix the highlighted clinic-data errors",
  },
  ar: {
    pageTitle: "إدارة العيادة · {name}",
    connector: "الموصل",
    back: "رجوع",
    // Account & WhatsApp card
    accountWhatsapp: "الحساب وواتساب",
    name: "الاسم",
    slug: "المعرّف",
    immutable: "غير قابل للتغيير",
    timezone: "المنطقة الزمنية",
    waPhoneNumberId: "معرّف رقم واتساب",
    waAccessToken: "رمز وصول واتساب",
    waTokenSet: "•••• مُعيّن — اتركه فارغًا للإبقاء",
    waTokenNotSet: "غير مُعيّن",
    staffUsername: "اسم مستخدم الموظف",
    staffPassword: "كلمة مرور الموظف",
    blankKeeps: "اتركه فارغًا للإبقاء",
    // Clinic data
    clinicData: "بيانات العيادة",
    fixBeforeSaving: "صحّح ما يلي قبل الحفظ:",
    saveClinic: "حفظ العيادة",
    // Danger zone
    dangerZone: "منطقة الخطر",
    deleteWarning: "احذف هذه العيادة وكل بياناتها نهائيًا. اكتب المعرّف {slug} للتأكيد.",
    confirmSlug: "أكّد المعرّف",
    deleteClinic: "حذف العيادة",
    defaultCannotDelete: "لا يمكن حذف المستأجر الافتراضي.",
    // Toasts
    clinicSaved: "تم حفظ العيادة",
    savedWithWarnings: "تم الحفظ ({n} تحذير)",
    clinicDeleted: "تم حذف العيادة",
    saveFailed: "فشل الحفظ",
    deleteFailed: "فشل الحذف",
    fixHighlighted: "يرجى تصحيح أخطاء بيانات العيادة المميّزة",
  },
};
