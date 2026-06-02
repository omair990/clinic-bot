// Missed Visits page: detection & recovery outreach. Visible copy only — stage/action
// keys and server values keep their logic. Terms follow the glossary.
export default {
  en: {
    title: "Missed Visits",
    subtitle: "Detection & recovery outreach",
    // KPI cards
    kpiMissedThisMonth: "Missed this month",
    kpiNeedsOutreach: "Needs outreach",
    kpiInRecovery: "In recovery",
    kpiRecovered: "Recovered",
    // Cards
    recoveryFunnel: "Recovery funnel",
    legendNeedsOutreach: "Needs outreach",
    legendInRecovery: "In recovery",
    legendRecovered: "Recovered",
    legendInactive: "Inactive",
    upcomingRisk: "Upcoming risk",
    riskLow: "Low",
    riskMedium: "Medium",
    riskHigh: "High",
    whyMissed: "Why patients missed",
    noReasons: "No reasons recorded yet.",
    // Filters
    filterAll: "All",
    filterNeedsOutreach: "Needs outreach",
    filterInRecovery: "In recovery",
    filterRecovered: "Recovered",
    filterInactive: "Inactive",
    // Search
    searchPlaceholder: "Search by patient, phone, service, doctor or reason…",
    // Action tooltips
    tipSend: "Send recovery message",
    tipResend: "Resend",
    tipResolve: "Mark resolved",
    tipInactive: "Mark inactive",
    // Detail dialog field labels
    detailMissedAppointment: "Missed appointment",
    detailService: "Service",
    detailRisk: "Missed-visit risk",
    detailReason: "Reason",
    detailOutcome: "Outcome",
    detailDetected: "Detected",
    // Detail buttons
    btnSend: "Send",
    btnResend: "Resend",
    btnResolve: "Resolve",
    btnInactive: "Inactive",
    // Day header prefix
    missedPrefix: "Missed · {label}",
    // Empty states
    emptyNone: "No missed visits — nice.",
    emptyFiltered: "No missed visits match your filters.",
    // Confirm dialog title
    confirmTitle: "Confirm action",
    // ACTION_META — labels, done toasts, confirm messages
    sendMessage: "Send message",
    resendMessage: "Resend message",
    markResolved: "Mark resolved",
    markInactive: "Mark inactive",
    sentDone: "Recovery message sent",
    resentDone: "Recovery message resent",
    resolvedDone: "Marked resolved",
    inactiveDone: "Marked inactive",
    sendMsg: "Send the recovery message to {n} on WhatsApp now?",
    resendMsg: "Resend the recovery message to {n} on WhatsApp?",
    resolveMsg: "Mark {n}'s missed visit as resolved? This closes the recovery — no message is sent.",
    inactiveMsg: "Mark {n} as inactive? This stops all recovery outreach for this missed visit.",
    actionFailed: "Action failed",
    done: "Done",
  },
  ar: {
    title: "الزيارات الفائتة",
    subtitle: "الرصد والتواصل للاسترجاع",
    // KPI cards
    kpiMissedThisMonth: "الفائتة هذا الشهر",
    kpiNeedsOutreach: "بحاجة لتواصل",
    kpiInRecovery: "قيد الاسترجاع",
    kpiRecovered: "تم الاسترجاع",
    // Cards
    recoveryFunnel: "مسار الاسترجاع",
    legendNeedsOutreach: "بحاجة لتواصل",
    legendInRecovery: "قيد الاسترجاع",
    legendRecovered: "تم الاسترجاع",
    legendInactive: "غير نشط",
    upcomingRisk: "المخاطر القادمة",
    riskLow: "منخفض",
    riskMedium: "متوسط",
    riskHigh: "مرتفع",
    whyMissed: "أسباب تفويت المرضى",
    noReasons: "لا توجد أسباب مسجّلة بعد.",
    // Filters
    filterAll: "الكل",
    filterNeedsOutreach: "بحاجة لتواصل",
    filterInRecovery: "قيد الاسترجاع",
    filterRecovered: "تم الاسترجاع",
    filterInactive: "غير نشط",
    // Search
    searchPlaceholder: "ابحث بالمريض أو الهاتف أو الخدمة أو الطبيب أو السبب…",
    // Action tooltips
    tipSend: "إرسال رسالة استرجاع",
    tipResend: "إعادة الإرسال",
    tipResolve: "وضع كمُعالَج",
    tipInactive: "وضع كغير نشط",
    // Detail dialog field labels
    detailMissedAppointment: "الموعد الفائت",
    detailService: "الخدمة",
    detailRisk: "خطر تفويت الزيارة",
    detailReason: "السبب",
    detailOutcome: "النتيجة",
    detailDetected: "تم الرصد",
    // Detail buttons
    btnSend: "إرسال",
    btnResend: "إعادة الإرسال",
    btnResolve: "معالجة",
    btnInactive: "غير نشط",
    // Day header prefix
    missedPrefix: "فائتة · {label}",
    // Empty states
    emptyNone: "لا توجد زيارات فائتة — رائع.",
    emptyFiltered: "لا توجد زيارات مطابقة للتصفية.",
    // Confirm dialog title
    confirmTitle: "تأكيد الإجراء",
    // ACTION_META — labels, done toasts, confirm messages
    sendMessage: "إرسال رسالة",
    resendMessage: "إعادة إرسال الرسالة",
    markResolved: "وضع كمُعالَج",
    markInactive: "وضع كغير نشط",
    sentDone: "تم إرسال رسالة الاسترجاع",
    resentDone: "تمت إعادة إرسال الرسالة",
    resolvedDone: "تمت المعالجة",
    inactiveDone: "تم وضعه كغير نشط",
    sendMsg: "هل تريد إرسال رسالة الاسترجاع إلى {n} عبر واتساب الآن؟",
    resendMsg: "إعادة إرسال رسالة الاسترجاع إلى {n} عبر واتساب؟",
    resolveMsg: "وضع زيارة {n} الفائتة كمُعالَجة؟ هذا يُنهي الاسترجاع دون إرسال أي رسالة.",
    inactiveMsg: "وضع {n} كغير نشط؟ هذا يوقف كل تواصل الاسترجاع لهذه الزيارة.",
    actionFailed: "فشل الإجراء",
    done: "تم",
  },
};
