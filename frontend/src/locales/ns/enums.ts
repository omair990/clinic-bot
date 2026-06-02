// Shared server-enum value labels shown in chips across pages.
export default {
  en: {
    status: { active: "Active", suspended: "Suspended", expired: "Expired" },
    stage: { detected: "Detected", notified: "Notified", followed_up: "Followed up", resolved: "Resolved", inactive: "Inactive" },
    risk: { low: "low", medium: "medium", high: "high" },
    appt: { confirmed: "Confirmed", completed: "Completed", cancelled: "Cancelled", no_show: "Missed" },
  },
  ar: {
    status: { active: "نشط", suspended: "موقوف", expired: "منتهٍ" },
    stage: { detected: "تم الرصد", notified: "تم الإشعار", followed_up: "تمت المتابعة", resolved: "تمت المعالجة", inactive: "غير نشط" },
    risk: { low: "منخفض", medium: "متوسط", high: "مرتفع" },
    appt: { confirmed: "مؤكد", completed: "مكتمل", cancelled: "ملغى", no_show: "فائت" },
  },
};
