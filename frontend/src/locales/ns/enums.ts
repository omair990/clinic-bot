// Shared server-enum value labels shown in chips across pages.
export default {
  en: {
    status: { active: "Active", suspended: "Suspended", expired: "Expired" },
    stage: { detected: "Detected", notified: "Notified", followed_up: "Followed up", resolved: "Resolved", inactive: "Inactive" },
    risk: { low: "low", medium: "medium", high: "high" },
    appt: { confirmed: "Confirmed", completed: "Completed", cancelled: "Cancelled", no_show: "Missed" },
    intent: {
      appointment: "Appointment", booking: "Booking", reschedule: "Reschedule",
      cancel: "Cancellation", emergency: "Emergency", handover: "Handover",
      complaint: "Complaint", no_show: "Missed visit", error: "Technical error",
      chat: "General chat", faq: "FAQ", pricing: "Pricing", insurance: "Insurance",
      greeting: "Greeting", other: "Other",
    },
  },
  ar: {
    status: { active: "نشط", suspended: "موقوف", expired: "منتهٍ" },
    stage: { detected: "تم الرصد", notified: "تم الإشعار", followed_up: "تمت المتابعة", resolved: "تمت المعالجة", inactive: "غير نشط" },
    risk: { low: "منخفض", medium: "متوسط", high: "مرتفع" },
    appt: { confirmed: "مؤكد", completed: "مكتمل", cancelled: "ملغى", no_show: "فائت" },
    intent: {
      appointment: "حجز موعد", booking: "حجز", reschedule: "إعادة جدولة",
      cancel: "إلغاء", emergency: "طارئ", handover: "تحويل لموظف",
      complaint: "شكوى", no_show: "زيارة فائتة", error: "خطأ تقني",
      chat: "محادثة عامة", faq: "أسئلة شائعة", pricing: "الأسعار", insurance: "التأمين",
      greeting: "تحية", other: "أخرى",
    },
  },
};
