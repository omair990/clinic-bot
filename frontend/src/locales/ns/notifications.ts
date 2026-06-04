// Full-page Notifications center (sidebar destination). The bell popover keeps its own
// short copy in ./bell.ts; this is the expanded list + category filters.
export default {
  en: {
    title: "Notifications",
    subtitle: "Everything the assistant and your clinic flagged, newest first.",
    markAllRead: "Mark all read",
    clearAll: "Clear",
    empty: "You're all caught up — new activity shows here in real time.",
    filterAll: "All",
    unreadCount: "{n} unread",
    // category labels (server `category` values)
    cat: {
      handover: "Handovers",
      booking: "Bookings",
      review: "Reviews",
      no_show: "Missed visits",
      incident: "Issues",
      general: "General",
    },
  },
  ar: {
    title: "الإشعارات",
    subtitle: "كل ما نبّه إليه المساعد أو عيادتك، الأحدث أولًا.",
    markAllRead: "تعليم الكل كمقروء",
    clearAll: "مسح",
    empty: "لا جديد لديك — يظهر النشاط الجديد هنا فوريًا.",
    filterAll: "الكل",
    unreadCount: "{n} غير مقروء",
    cat: {
      handover: "التحويلات",
      booking: "الحجوزات",
      review: "التقييمات",
      no_show: "الزيارات الفائتة",
      incident: "المشكلات",
      general: "عام",
    },
  },
};
