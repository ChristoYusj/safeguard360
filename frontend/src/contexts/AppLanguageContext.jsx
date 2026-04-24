import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import {
  APP_SETTINGS_UPDATED_EVENT,
  readAppSettings,
} from "../utils/appSettings";

const translations = {
  "en-US": {
    app_name: "SafeGuard 360",
    platform_tagline: "Unified AI Safety & Operations Platform",
    command_center: "Command Center",
    session: "Session",
    authorized_operator: "Authorized Operator",
    system_online: "System Online",
    collapse: "Collapse",
    fleet_monitoring: "Fleet Monitoring",
    attendance_ppe: "Attendance & PPE",
    logs: "Logs",
    ai_chatbot: "AI Chatbot",
    settings: "Settings",
    system_access: "System Access",
    enter_credentials: "Enter your credentials to access the command center",
    email: "Email",
    enter_account_email: "Enter account email",
    access_key: "Access Key",
    enter_access_key: "Enter access key",
    sign_in: "Sign In",
    system_status_operational: "System Status: Operational",
    open_module: "Open module",
    drivers_module: "Drivers",
    drivers_module_description:
      "Real-time fleet monitoring and driver fatigue detection",
    attendance_module_description:
      "Track check-ins, PPE verification, and shift management",
    logs_module_description: "System audit trail and session history",
    ai_chatbot_description: "Intelligent assistant for operations support",
    settings_module_description: "System configuration and workspace preferences",
    footer_notice:
      "© 2026 SafeGuard 360. All rights reserved. Authorized personnel only.",
    unified_audit_trail: "Unified Audit Trail",
    platform_logs: "Platform Logs",
    attendance_detection: "Attendance & PPE Detection",
    platform_configuration: "Platform Configuration",
    workspace_controls: "Workspace Controls",
    theme_preference: "Theme Preference",
    theme_preference_description: "",
    dark_command_center: "Dark command center",
    light_command_center: "Light command center",
    language: "Language",
    language_description: "",
    camera: "Camera",
    fleet_camera_description:
      "Choose the default camera source that fleet monitoring should preselect.",
    attendance_camera_description:
      "Choose the default video source for attendance and PPE scans.",
    driver_database: "Driver Database",
    driver_database_description: "",
    worker_database: "Worker Database",
    worker_database_description: "",
    add_driver: "+ Add Driver",
    add_worker: "+ Add Worker",
    driver_name_placeholder: "Driver name",
    driver_id_placeholder: "Driver ID",
    worker_name_placeholder: "Worker name",
    worker_id_placeholder: "Worker badge or ID",
    profile_picture: "Profile Picture",
    profile_picture_description:
      "PNG only. If you do not upload one, the default profile image is used.",
    save_driver: "Save Driver",
    save_worker: "Save Worker",
    save_changes: "Save Changes",
    cancel: "Cancel",
    edit: "Edit",
    delete: "Delete",
    no_drivers_yet: "No drivers have been added yet.",
    no_workers_yet: "No workers have been added yet.",
    current_session: "Current Session",
    account: "Account",
    signed_in_email: "Signed-in email",
    account_type: "Account type",
    reset_password: "Reset Password",
    contact_dashboard_support: "Contact Dashboard Support",
    core_services: "Core Services",
  },
  "ar-LB": {
    app_name: "سيف غارد 360",
    platform_tagline: "منصة موحّدة للسلامة والعمليات بالذكاء الاصطناعي",
    command_center: "مركز القيادة",
    session: "الجلسة",
    authorized_operator: "مشغّل معتمد",
    system_online: "النظام يعمل",
    collapse: "تصغير",
    fleet_monitoring: "مراقبة الأسطول",
    attendance_ppe: "الحضور ومعدات الوقاية",
    logs: "السجلات",
    ai_chatbot: "المحادث الذكي",
    settings: "الإعدادات",
    system_access: "دخول النظام",
    enter_credentials: "أدخل بياناتك للوصول إلى مركز القيادة",
    email: "البريد الإلكتروني",
    enter_account_email: "أدخل بريد الحساب",
    access_key: "مفتاح الوصول",
    enter_access_key: "أدخل مفتاح الوصول",
    sign_in: "تسجيل الدخول",
    system_status_operational: "حالة النظام: يعمل",
    open_module: "فتح الوحدة",
    drivers_module: "السائقون",
    drivers_module_description: "مراقبة الأسطول والتنبيه إلى إرهاق السائقين",
    attendance_module_description:
      "متابعة تسجيل الحضور والتحقق من معدات الوقاية وإدارة الدوام",
    logs_module_description: "سجل تدقيق النظام وتاريخ الجلسات",
    ai_chatbot_description: "مساعد ذكي لدعم العمليات",
    settings_module_description: "إعدادات النظام وتفضيلات مساحة العمل",
    footer_notice:
      "© 2026 سيف غارد 360. جميع الحقوق محفوظة. للاستخدام من قبل المصرّح لهم فقط.",
    unified_audit_trail: "سجل التدقيق الموحّد",
    platform_logs: "سجلات المنصة",
    attendance_detection: "اكتشاف الحضور ومعدات الوقاية",
    platform_configuration: "إعدادات المنصة",
    workspace_controls: "عناصر التحكم في مساحة العمل",
    theme_preference: "المظهر",
    theme_preference_description: "بدّل بين النمط الفاتح والداكن لمركز القيادة.",
    dark_command_center: "مركز قيادة داكن",
    light_command_center: "مركز قيادة فاتح",
    language: "اللغة",
    language_description: "حدّد اللغة الافتراضية لواجهة المشغّل.",
    camera: "الكاميرا",
    fleet_camera_description:
      "اختر مصدر الكاميرا الافتراضي الذي تفتحه مراقبة الأسطول تلقائياً.",
    attendance_camera_description:
      "اختر مصدر الفيديو الافتراضي للحضور وفحص معدات الوقاية.",
    driver_database: "قاعدة بيانات السائقين",
    driver_database_description: "",
    worker_database: "قاعدة بيانات العمال",
    worker_database_description: "",
    add_driver: "+ إضافة سائق",
    add_worker: "+ إضافة عامل",
    driver_name_placeholder: "اسم السائق",
    driver_id_placeholder: "معرّف السائق",
    worker_name_placeholder: "اسم العامل",
    worker_id_placeholder: "بطاقة العامل أو المعرّف",
    profile_picture: "الصورة الشخصية",
    profile_picture_description:
      "PNG فقط. إذا لم ترفع صورة سيتم استخدام الصورة الافتراضية.",
    save_driver: "حفظ السائق",
    save_worker: "حفظ العامل",
    save_changes: "حفظ التعديلات",
    cancel: "إلغاء",
    edit: "تعديل",
    delete: "حذف",
    no_drivers_yet: "لا يوجد سائقون مضافون بعد.",
    no_workers_yet: "لا يوجد عمّال مضافون بعد.",
    current_session: "الجلسة الحالية",
    account: "الحساب",
    signed_in_email: "البريد الإلكتروني المسجّل",
    account_type: "نوع الحساب",
    reset_password: "إعادة تعيين كلمة المرور",
    contact_dashboard_support: "التواصل مع دعم المنصة",
    core_services: "الخدمات الأساسية",
  },
};

const AppLanguageContext = createContext(null);

function normalizeLanguage(language) {
  return language?.startsWith("ar") ? "ar-LB" : "en-US";
}

export function AppLanguageProvider({ children }) {
  const [language, setLanguage] = useState(() =>
    normalizeLanguage(readAppSettings().language),
  );

  useEffect(() => {
    const syncLanguage = () => {
      setLanguage(normalizeLanguage(readAppSettings().language));
    };

    window.addEventListener(APP_SETTINGS_UPDATED_EVENT, syncLanguage);
    window.addEventListener("storage", syncLanguage);

    return () => {
      window.removeEventListener(APP_SETTINGS_UPDATED_EVENT, syncLanguage);
      window.removeEventListener("storage", syncLanguage);
    };
  }, []);

  const locale = language === "ar-LB" ? "ar-LB" : "en-US";
  const isArabic = language === "ar-LB";

  useEffect(() => {
    if (typeof document === "undefined") {
      return;
    }

    document.documentElement.lang = language;
    document.documentElement.dir = isArabic ? "rtl" : "ltr";
    document.body.dir = isArabic ? "rtl" : "ltr";
  }, [isArabic, language]);

  const value = useMemo(() => {
    const activeTranslations = translations[language] || translations["en-US"];
    const fallbackTranslations = translations["en-US"];

    return {
      language,
      locale,
      isArabic,
      t: (key, fallback) =>
        activeTranslations[key] || fallbackTranslations[key] || fallback || key,
    };
  }, [isArabic, language, locale]);

  return (
    <AppLanguageContext.Provider value={value}>
      {children}
    </AppLanguageContext.Provider>
  );
}

export function useAppLanguage() {
  const context = useContext(AppLanguageContext);

  if (!context) {
    throw new Error("useAppLanguage must be used within AppLanguageProvider");
  }

  return context;
}
