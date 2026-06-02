// Clinic data editor: tabbed editor for clinic info, services, doctors, FAQs,
// policy and notification recipients. Visible copy only — data keys, DAYS values
// and binding logic are unchanged. Terms follow the glossary.
export default {
  en: {
    // Tabs
    tabClinicInfo: "Clinic info",
    tabServices: "Services ({n})",
    tabDoctors: "Doctors ({n})",
    tabFaqs: "FAQs ({n})",
    tabPolicy: "Policy",
    tabNotifications: "Notifications ({n})",
    // Clinic info
    clinicName: "Clinic name *",
    address: "Address",
    phone: "Phone",
    languages: "Languages",
    defaultLanguage: "Default agent language",
    defaultLanguageHelper:
      "What the assistant replies in when the patient's language is unclear. It still matches the patient whenever they clearly use a language.",
    autoMatch: "Auto (always match the patient)",
    // Services
    name: "Name *",
    priceSar: "Price (SAR) *",
    durationMin: "Duration (min) *",
    addService: "Add service",
    // Doctors
    specialty: "Specialty *",
    availableDays: "Available days *",
    hours: "Hours *",
    addDoctor: "Add doctor",
    // FAQs
    question: "Question",
    answer: "Answer",
    addFaq: "Add FAQ",
    // Policy
    bookingLeadTime: "Booking lead time (hours)",
    cancellationNotice: "Cancellation notice (hours)",
    walkInsAccepted: "Walk-ins accepted",
    paymentMethods: "Payment methods",
    policyNote:
      "Other sections (branches, booking fields, connector) are preserved automatically.",
    // Notifications
    notifIntroBefore:
      "People at this clinic who get WhatsApp notifications. ",
    notifIntroEscalations: "Escalations",
    notifIntroMiddle:
      " covers handovers, emergencies and new bookings; ",
    notifIntroDigest: "Digest",
    notifIntroAfter:
      " is the daily/weekly insights summary. Add as many as you like (e.g. front desk + owner). Use full international numbers, e.g. ",
    label: "Label",
    whatsappNumber: "WhatsApp number",
    escalations: "Escalations",
    digest: "Digest",
    addRecipient: "Add recipient",
    ownerPlaceholder: "Owner",
    numberPlaceholder: "9665XXXXXXXX",
  },
  ar: {
    // Tabs
    tabClinicInfo: "معلومات العيادة",
    tabServices: "الخدمات ({n})",
    tabDoctors: "الأطباء ({n})",
    tabFaqs: "الأسئلة الشائعة ({n})",
    tabPolicy: "السياسة",
    tabNotifications: "الإشعارات ({n})",
    // Clinic info
    clinicName: "اسم العيادة *",
    address: "العنوان",
    phone: "الهاتف",
    languages: "اللغات",
    defaultLanguage: "لغة المساعد الافتراضية",
    defaultLanguageHelper:
      "اللغة التي يردّ بها المساعد عندما تكون لغة المريض غير واضحة. وسيظل يطابق لغة المريض كلما استخدم لغة بوضوح.",
    autoMatch: "تلقائي (مطابقة لغة المريض دائمًا)",
    // Services
    name: "الاسم *",
    priceSar: "السعر (ريال) *",
    durationMin: "المدة (دقيقة) *",
    addService: "إضافة خدمة",
    // Doctors
    specialty: "التخصص *",
    availableDays: "أيام التوفّر *",
    hours: "الساعات *",
    addDoctor: "إضافة طبيب",
    // FAQs
    question: "السؤال",
    answer: "الإجابة",
    addFaq: "إضافة سؤال",
    // Policy
    bookingLeadTime: "مهلة الحجز (ساعات)",
    cancellationNotice: "مهلة الإلغاء (ساعات)",
    walkInsAccepted: "قبول الزيارات بدون موعد",
    paymentMethods: "طرق الدفع",
    policyNote:
      "يتم الحفاظ على الأقسام الأخرى (الفروع، حقول الحجز، الموصل) تلقائيًا.",
    // Notifications
    notifIntroBefore:
      "الأشخاص في هذه العيادة الذين يتلقّون إشعارات واتساب. ",
    notifIntroEscalations: "التصعيدات",
    notifIntroMiddle: " تشمل التحويلات والطوارئ والحجوزات الجديدة؛ و",
    notifIntroDigest: "الملخص",
    notifIntroAfter:
      " هو ملخص التحليلات اليومي/الأسبوعي. أضف ما تشاء (مثل الاستقبال + المالك). استخدم أرقامًا دولية كاملة، مثل ",
    label: "التسمية",
    whatsappNumber: "رقم واتساب",
    escalations: "التصعيدات",
    digest: "الملخص",
    addRecipient: "إضافة مستلِم",
    ownerPlaceholder: "المالك",
    numberPlaceholder: "9665XXXXXXXX",
  },
};
