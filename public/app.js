const themeStorageKey = "officeFormsTheme";
const defaultTheme = "dark";

function getInitialTheme() {
  const storedTheme = localStorage.getItem(themeStorageKey);
  return storedTheme === "light" || storedTheme === "dark" ? storedTheme : defaultTheme;
}

const state = {
  worker: null,
  token: localStorage.getItem("token") || null,
  theme: getInitialTheme(),
  submissions: [],
  calendarEntries: [],
  otherForms: [],
  calendarDate: new Date(),
  selectedForm: "AL",
  kpiStep: 0,
  kpiValidationAttempted: false,
  draftsRestored: false,
  editSubmission: null,
  editFormKey: null
};

const formIdBySubmissionType = {
  AL: "AL",
  EL: "AL",
  MC: "MC",
  KPI: "KPI",
  EXP: "EXP",
  OT: "OT"
};
const formKeyBySubmissionType = {
  AL: "al",
  EL: "al",
  MC: "mc",
  KPI: "kpi",
  EXP: "expense",
  OT: "ot"
};
const generateButtons = () => ({
  al: elements.generateButton,
  mc: elements.mcGenerateButton,
  kpi: elements.kpiGenerateButton,
  expense: elements.expenseGenerateButton,
  ot: elements.otGenerateButton
});

let editBanner = null;
function ensureEditBanner() {
  if (editBanner) return editBanner;
  editBanner = document.createElement("div");
  editBanner.className = "edit-banner hidden";
  editBanner.innerHTML = `
    <span class="edit-banner-text"></span>
    <button class="edit-banner-cancel" type="button">Cancel edit</button>
  `;
  editBanner.querySelector(".edit-banner-cancel").addEventListener("click", cancelEdit);
  const formsPanel = document.querySelector("#formsPanel");
  formsPanel.insertBefore(editBanner, formsPanel.firstChild);
  return editBanner;
}

function showEditBanner(submission) {
  const banner = ensureEditBanner();
  banner.querySelector(".edit-banner-text").textContent =
    `Editing ${submission.formType} ${submission.formName || ""} (submitted ${submission.createdAt ? new Date(submission.createdAt).toLocaleString() : ""}). Submit to update.`;
  banner.classList.remove("hidden");
}

function hideEditBanner() {
  if (editBanner) editBanner.classList.add("hidden");
}

function startEdit(submission) {
  if (!submission) return;
  const formKey = formKeyBySubmissionType[submission.formType];
  const formId = formIdBySubmissionType[submission.formType];
  if (!formKey || !formId) return;
  state.editSubmission = submission;
  state.editFormKey = formKey;
  const draftObj = submissionToDraft(submission, formKey);
  drafts[formKey].restore(draftObj);
  const buttons = generateButtons();
  const btn = buttons[formKey];
  if (btn) {
    btn.dataset.originalLabel = btn.dataset.originalLabel || btn.textContent;
    btn.textContent = `Update ${btn.dataset.originalLabel.replace(/^Generate /, "")}`;
  }
  selectForm(formId);
  setActiveTab("formsPanel");
  showEditBanner(submission);
  setMessage(messageElForFormKey(formKey), `Editing existing ${submission.formType} submission. Make changes and submit to update.`, "info");
}

function cancelEdit() {
  if (!state.editSubmission && !state.editFormKey) return;
  const formKey = state.editFormKey;
  state.editSubmission = null;
  state.editFormKey = null;
  const buttons = generateButtons();
  const btn = formKey ? buttons[formKey] : null;
  if (btn && btn.dataset.originalLabel) btn.textContent = btn.dataset.originalLabel;
  hideEditBanner();
  if (formKey) {
    setMessage(messageElForFormKey(formKey), "Edit cancelled.", "info");
  }
}

function clearEditAfterSubmit(formKey) {
  state.editSubmission = null;
  state.editFormKey = null;
  const buttons = generateButtons();
  const btn = formKey ? buttons[formKey] : null;
  if (btn) {
    setButtonLoading(btn, false);
    if (btn.dataset.originalLabel) btn.textContent = btn.dataset.originalLabel;
  }
  hideEditBanner();
}

function messageElForFormKey(formKey) {
  return {
    al: elements.formMessage,
    mc: elements.mcFormMessage,
    kpi: elements.kpiFormMessage,
    expense: elements.expenseFormMessage,
    ot: elements.otFormMessage
  }[formKey];
}

function isEditingForm(formKey) {
  return !!state.editSubmission && state.editFormKey === formKey;
}

function submissionEditEndpoint() {
  return `/api/submissions/${encodeURIComponent(state.editSubmission.id)}`;
}

function submissionToDraft(submission, formKey) {
  if (formKey === "al") {
    return {
      startDate: submission.startDate,
      endDate: submission.endDate,
      leaveType: submission.leaveType || "annual",
      reason: submission.reason || "",
      halfDay: !!submission.isHalfDay && submission.startDate === submission.endDate,
      halfDayPeriod: submission.halfDayPeriod || "AM",
      removeEntitlement: !!(submission.leaveSummary && submission.leaveSummary.remove_entitlement)
    };
  }
  if (formKey === "mc") {
    return {
      startDate: submission.startDate,
      endDate: submission.endDate,
      reason: submission.reason || ""
    };
  }
  if (formKey === "kpi") {
    const data = submission.kpiData || {};
    const scores = {};
    if (data.scores && typeof data.scores === "object") {
      Object.entries(data.scores).forEach(([sectionKey, list]) => {
        if (Array.isArray(list)) {
          list.forEach((value, index) => {
            scores[`${sectionKey}-${index}`] = value;
          });
        }
      });
    }
    return {
      month: submission.kpiMonth || "",
      evaluatorName: data.evaluatorName || "",
      taskList: data.taskList || "",
      workerFeedback: data.workerFeedback || "",
      trainingNeeds: data.trainingNeeds || "",
      evaluatorFeedback: data.evaluatorFeedback || "",
      scores,
      comments: data.comments || {},
      options: data.summaryOptions || {},
      step: 0
    };
  }
  if (formKey === "expense") {
    const data = submission.expenseData || {};
    const rows = (data.items || []).map(item => {
      const row = {};
      expenseColumns.forEach(col => {
        const value = item[col.key];
        row[col.key] = value === null || value === undefined ? "" : String(value);
      });
      return row;
    });
    return {
      month: data.claimMonth || "",
      monthEnd: data.claimMonthEnd || "",
      site: data.site || "",
      supervisorName: data.supervisorName || "",
      advances: data.advances === null || data.advances === undefined ? "" : String(data.advances),
      rows
    };
  }
  if (formKey === "ot") {
    const data = submission.otData || {};
    const rows = (data.items || []).map(item => {
      const row = {};
      otColumns.forEach(col => {
        if (col.key === "hours") return;
        const value = item[col.key];
        row[col.key] = value === null || value === undefined ? "" : String(value);
      });
      return row;
    });
    return {
      month: data.claimMonth || "",
      monthEnd: data.claimMonthEnd || "",
      rows
    };
  }
  return null;
}

document.documentElement.dataset.theme = state.theme;

const leaveTypeLabels = {
  annual: "Annual Leave",
  unpaid: "Unpaid Leave",
  emergency: "Emergency Leave",
  other: "Others"
};

const alDeductingLeaveTypes = new Set(["annual", "emergency"]);
const calendarTypeLabels = {
  AL: "Annual Leave",
  EL: "Emergency Leave",
  MC: "Medical Certificate"
};
const companyHolidays = [
  { date: "2026-01-01", name: "Tahun Baru" },
  { date: "2026-02-01", name: "Thaipusam" },
  { date: "2026-02-02", name: "Thaipusam (Cuti Gantian)" },
  { date: "2026-02-17", name: "Tahun Baru Cina" },
  { date: "2026-02-18", name: "Tahun Baru Cina" },
  { date: "2026-03-07", name: "Nuzul Quran *" },
  { date: "2026-03-21", name: "Hari Raya Aidilfitri *" },
  { date: "2026-03-22", name: "Hari Raya Aidilfitri *" },
  { date: "2026-03-23", name: "Hari Raya Aidilfitri * (Cuti Gantian)" },
  { date: "2026-05-01", name: "Hari Pekerja" },
  { date: "2026-05-27", name: "Hari Raya Aidil Adha *" },
  { date: "2026-05-31", name: "Hari Wesak" },
  { date: "2026-06-01", name: "Hari Keputeraan Yang di-Pertuan Agong" },
  { date: "2026-06-02", name: "Hari Wesak (Cuti Gantian)" },
  { date: "2026-06-17", name: "Awal Muharam (Maal Hijrah)" },
  { date: "2026-08-25", name: "Maulidur Rasul" },
  { date: "2026-08-31", name: "Hari Kemerdekaan" },
  { date: "2026-09-16", name: "Hari Malaysia" },
  { date: "2026-11-08", name: "Deepavali" },
  { date: "2026-11-09", name: "Deepavali (Cuti Gantian)" },
  { date: "2026-12-11", name: "Hari Keputeraan Sultan Selangor" },
  { date: "2026-12-25", name: "Hari Krismas" }
];
const companyHolidayByDate = new Map(companyHolidays.map(holiday => [holiday.date, holiday]));
const kpiSections = [
  {
    key: "knowledge",
    title: "Pengetahuan Dan Kemahiran",
    items: [
      "Pemahaman teori dan pengetahuan praktikal dalam bidang tugas",
      "Menggunakan kepakaran untuk menambahbaik tugasan yang diberi",
      "Berkongsi pengetahuan dan kemahiran dengan ahli pasukan",
      "Pengetahuan tentang perkara baharu atau perubahan dalam bidang tugas",
      "Kepatuhan kepada polisi dan prosedur syarikat"
    ]
  },
  {
    key: "quality",
    title: "Kualiti Kerja",
    items: [
      "Kualiti dan hasil kerja",
      "Kekemasan dan ketelitian dalam menghasilkan tugas",
      "Membuat penambahbaikan dalam tugasan",
      "Kemahiran menulis (laporan/surat/proposal/etc)",
      "Penggunaan masa untuk menghasilkan tugasan"
    ]
  },
  {
    key: "problemSolving",
    title: "Kemahiran Menyelesaikan Masalah",
    items: [
      "Kebolehan menyelesaikan masalah dengan cekap",
      "Kebolehan menyelesaikan masalah tanpa bantuan penyelia",
      "Kebolehan memberi penerangan kepada jalan penyelesaian",
      "Menyelesaikan isu dan masalah klien dengan berkesan dan cekap",
      "Tetap tenang semasa menghadapi konflik"
    ]
  },
  {
    key: "communication",
    title: "Kemahiran Berkomunikasi",
    items: [
      "Kebolehan menyampaikan sesuatu maklumat",
      "Kebolehan mendengar dan menerima maklumat dari orang lain",
      "Bersikap positif ketika berinteraksi",
      "Mewujudkan suasana harmoni dan mesra semasa berkomunikasi",
      "Penerimaan terhadap kritikan"
    ]
  },
  {
    key: "teamwork",
    title: "Pasukan",
    items: [
      "Keupayaan untuk mendengar dan mengikuti arahan",
      "Bekerjasama dan membantu semasa diperlukan",
      "Seorang yang komited dan aktif",
      "Berkomunikasi dan memberikan idea dan cadangan",
      "Kebolehpercayaan jika diberi tugasan"
    ]
  },
  {
    key: "initiative",
    title: "Inisiatif",
    items: [
      "Kebolehan bekerja dibawah pengawasan yang minimum",
      "Kebolehan menentukan keutamaan kerja apabila semuanya penting",
      "Memaklumkan progress kerja kepada penyelia",
      "Mencari cara terbaik untuk menyelesaikan tugasan.",
      "Bersedia untuk menerima kerja tambahan"
    ]
  },
  {
    key: "continuousLearning",
    title: "Pembelajaran Berterusan & Pembangunan Kemahiran",
    items: [
      "Mempunyai matlamat jelas tentang masa depannya dan berusaha mencapainya",
      "Menunjukkan semangat belajar yang berterusan",
      "Mempraktikkan pengetahuan dan kemahiran yang baharu dalam bidang tugas",
      "Mencari peluang untuk mengembangkan pengetahuan dan kemahiran",
      "Berterusan menunjukkan kemajuan diri"
    ]
  }
];
const kpiOptionFields = [
  { key: "breakfastMeeting", label: "Breakfast Meeting", options: ["Pilih", "Hadir", "Tidak Hadir"] },
  { key: "emergencyLeaveAttendance", label: "Cuti Kecemasan (EL)", options: ["Pilih", "Tiada", "0.5 Hari", "1 Hari", "1.5 Hari", "2 Hari", "2.5 Hari", "Lebih 3 Hari"] },
  { key: "medicalLeaveAttendance", label: "Cuti Sakit (MC)", options: ["Pilih", "Tiada", "1 Hari", "2 Hari", "3 Hari", "4 Hari", "5 Hari", "Lebih 6 Hari"] },
  { key: "biroAgama", label: "Biro Agama", options: ["Pilih", "1", "2", "Tiada"] },
  { key: "biroSukan", label: "Biro Sukan", options: ["Pilih", "1", "2", "Tiada"] },
  { key: "trainingHours", label: "Sertai kursus/latihan sekurang-kurangnya 8 jam", options: ["Pilih", "Hadir", "Tiada"] },
  { key: "committeeRole", label: "Dilantik sebagai ahli jawatankuasa", options: ["Pilih", "Pengerusi", "Naib Pengerusi", "Setiausaha", "AJK", "Tiada"] },
  { key: "eqariah", label: "Kemaskini aktiviti dalam aplikasi EQariah", options: ["Pilih", "Ya", "Tiada"] }
];
const kpiStepOrder = ["overview", ...kpiSections.map(section => section.key), "summary", "feedback"];
const kpiScoreInstruction = {
  title: "Panduan skala penilaian",
  lines: [
    "Bahagian 1: Faktor Penilaian (80%). Isikan nombor skala dari 1 hingga 5 mengikut ruang yang disediakan.",
    "5 - Cemerlang: hasil kerja sentiasa mencapai dan melebihi tahap maksimum yang telah ditentukan.",
    "4 - Baik: hasil kerja kadangkala mencapai tahap maksimum yang telah ditentukan.",
    "3 - Sederhana: hasil kerja sentiasa melebihi tahap minimum yang telah ditentukan.",
    "2 - Lemah: hasil kerja kadangkala mencapai tahap minimum yang telah ditentukan.",
    "1 - Gagal: hasil kerja sentiasa di bawah tahap minimum yang telah ditentukan."
  ]
};
const kpiStepInstructions = {
  overview: {
    title: "Panduan borang penilaian",
    lines: [
      "Objektif borang: meningkatkan keberkesanan dan produktiviti, membincangkan prestasi dengan penyelia, mengenal pasti kekuatan dan kelemahan, mencadangkan program peningkatan, dan menyokong keputusan HR.",
      "Panduan penilai: tetapkan standard kerja yang spesifik, boleh diukur, boleh dicapai, realistik dan mempunyai tempoh masa.",
      "Jelaskan expectation prestasi, beri ruang komunikasi dua hala, dan pastikan penilaian adil serta telus.",
      "Senarai tugasan boleh disertakan dengan lampiran tambahan jika ruang tidak mencukupi."
    ]
  },
  summary: {
    title: "Panduan pemarkahan tambahan",
    lines: [
      "Bahagian 2: Kehadiran (10%) merangkumi Breakfast Meeting, Cuti Kecemasan (EL), dan Cuti Sakit (MC).",
      "Bahagian 3: Penglibatan aktiviti Biro (10%) merangkumi Biro Agama dan Biro Sukan.",
      "Bahagian 4: Nilai Tambah (10%) merangkumi latihan sekurang-kurangnya 8 jam dan peranan jawatankuasa.",
      "Bahagian 5: E-Qariah (10%) dinilai berdasarkan kemaskini aplikasi sebelum atau pada setiap 15hb."
    ]
  },
  feedback: {
    title: "Panduan maklumbalas",
    lines: [
      "Lengkapkan maklumbalas pekerja, keperluan latihan jika ada, dan maklumbalas penilai selepas semua bahagian pemarkahan diisi.",
      "Gunakan ruangan ini untuk mencatat tindakan susulan atau cadangan program peningkatan prestasi."
    ]
  }
};
const kpiOptionInstructions = {
  breakfastMeeting: "Kehadiran Breakfast Meeting dinilai sebagai sebahagian daripada Bahagian Kehadiran.",
  emergencyLeaveAttendance: "Rekod Cuti Kecemasan (EL) dinilai sebagai sebahagian daripada Bahagian Kehadiran.",
  medicalLeaveAttendance: "Rekod Cuti Sakit (MC) dinilai sebagai sebahagian daripada Bahagian Kehadiran.",
  biroAgama: "BIRO AGAMA = 5%. Kehadiran penuh memerlukan sekurang-kurangnya 2 aktiviti sebulan: Kelas Mengaji Online, Kuliah Mingguan, Bacaan Yasin, atau aktiviti agama persendirian yang dimaklumkan kepada AJK Biro Agama.",
  biroSukan: "BIRO SUKAN = 5%. Kehadiran penuh memerlukan sekurang-kurangnya 2 aktiviti sebulan: aktiviti berkumpulan, aktiviti lelaki, aktiviti perempuan, atau penggunaan fasiliti gym MSB yang dimaklumkan kepada AJK Biro Sukan.",
  trainingHours: "Menyertai program latihan sekurang-kurangnya 8 jam dalam sebulan = 5%.",
  committeeRole: "Dilantik sebagai ahli jawatankuasa ISO, Biro Agama, atau Biro Sukan = 5%.",
  eqariah: "Kemaskini aplikasi E-Qariah sebelum atau pada setiap 15hb."
};
const expenseInitialLineCount = 2;
const expenseMinLineCount = 1;
const expenseMaxLineCount = 13;
const expenseTransportModes = {
  car: { label: "Car", rate: 0.87 },
  motorcycle: { label: "Motorcycle", rate: 0.60 }
};
const expenseAmountFields = [
  "totalKm",
  "parking",
  "toll",
  "hotel",
  "flight",
  "medical",
  "phone",
  "entertainment",
  "travelAllowance",
  "misc"
];
const expenseColumnLabels = {
  date: "Date",
  description: "Description",
  project: "Project",
  totalKm: "KM",
  transportMode: "Transport",
  parking: "Parking",
  toll: "Toll",
  hotel: "Hotel",
  flight: "Flight",
  medical: "Medical",
  phone: "Phone",
  entertainment: "Ent'ment",
  travelAllowance: "Travel",
  misc: "Misc"
};
const expenseColumns = [
  { key: "date", type: "date" },
  { key: "description", type: "textarea", placeholder: "Travel purpose" },
  { key: "project", type: "text" },
  { key: "totalKm", type: "number", step: "0.1" },
  { key: "transportMode", type: "select" },
  { key: "parking", type: "number", step: "0.01" },
  { key: "toll", type: "number", step: "0.01" },
  { key: "hotel", type: "number", step: "0.01" },
  { key: "flight", type: "number", step: "0.01" },
  { key: "medical", type: "number", step: "0.01" },
  { key: "phone", type: "number", step: "0.01" },
  { key: "entertainment", type: "number", step: "0.01" },
  { key: "travelAllowance", type: "number", step: "0.01" },
  { key: "misc", type: "number", step: "0.01" }
];
const otInitialLineCount = 2;
const otMinLineCount = 1;
const otMaxLineCount = 17;
const otRateTypes = {
  normal: { label: "1.5x (normal day)", multiplier: 1.5 },
  rest: { label: "2x (rest day)", multiplier: 2 },
  holiday: { label: "3x (public holiday)", multiplier: 3 }
};
const otColumnLabels = {
  date: "Date",
  timeFrom: "From",
  timeTo: "To",
  rateType: "Rate",
  hours: "Hours",
  description: "Description"
};
const otColumns = [
  { key: "date", type: "date" },
  { key: "timeFrom", type: "text", placeholder: "1800" },
  { key: "timeTo", type: "text", placeholder: "2200" },
  { key: "rateType", type: "select" },
  { key: "hours", type: "readonly" },
  { key: "description", type: "textarea", placeholder: "Task assigned in detail" }
];
const elements = {
  loginView: document.querySelector("#loginView"),
  registerView: document.querySelector("#registerView"),
  profileSetupView: document.querySelector("#profileSetupView"),
  workspaceView: document.querySelector("#workspaceView"),
  loginForm: document.querySelector("#loginForm"),
  workerIdInput: document.querySelector("#workerIdInput"),
  loginPasswordInput: document.querySelector("#loginPasswordInput"),
  loginMessage: document.querySelector("#loginMessage"),
  showRegisterButton: document.querySelector("#showRegisterButton"),
  showLoginButton: document.querySelector("#showLoginButton"),
  registerForm: document.querySelector("#registerForm"),
  registerWorkerIdInput: document.querySelector("#registerWorkerIdInput"),
  registerPasswordInput: document.querySelector("#registerPasswordInput"),
  registerMessage: document.querySelector("#registerMessage"),
  profileSetupForm: document.querySelector("#profileSetupForm"),
  setupNameInput: document.querySelector("#setupNameInput"),
  setupCalendarNameInput: document.querySelector("#setupCalendarNameInput"),
  setupDesignationInput: document.querySelector("#setupDesignationInput"),
  setupDepartmentInput: document.querySelector("#setupDepartmentInput"),
  setupHouseTelInput: document.querySelector("#setupHouseTelInput"),
  setupOtherTelInput: document.querySelector("#setupOtherTelInput"),
  setupEvaluatorNameInput: document.querySelector("#setupEvaluatorNameInput"),
  setupEntitlementInput: document.querySelector("#setupEntitlementInput"),
  setupEmploymentTypeInput: document.querySelector("#setupEmploymentTypeInput"),
  setupEmploymentStartDateInput: document.querySelector("#setupEmploymentStartDateInput"),
  setupEmploymentEndDateInput: document.querySelector("#setupEmploymentEndDateInput"),
  saveProfileSetupButton: document.querySelector("#saveProfileSetupButton"),
  profileSetupMessage: document.querySelector("#profileSetupMessage"),
  workerName: document.querySelector("#workerName"),
  workerIdBadge: document.querySelector("#workerIdBadge"),
  workerDesignation: document.querySelector("#workerDesignation"),
  logoutButton: document.querySelector("#logoutButton"),
  themeToggles: document.querySelectorAll("[data-theme-toggle]"),
  tabs: document.querySelectorAll(".tab"),
  panels: document.querySelectorAll(".panel"),
  formCards: document.querySelector("#formCards"),
  formAreas: document.querySelectorAll("[data-form-area]"),
  profileName: document.querySelector("#profileName"),
  profileDesignation: document.querySelector("#profileDesignation"),
  profileHouseTel: document.querySelector("#profileHouseTel"),
  profileOtherPhone: document.querySelector("#profileOtherPhone"),
  profileBalance: document.querySelector("#profileBalance"),
  profileForm: document.querySelector("#profileForm"),
  profileWorkerIdInput: document.querySelector("#profileWorkerIdInput"),
  profileNameInput: document.querySelector("#profileNameInput"),
  profileCalendarNameInput: document.querySelector("#profileCalendarNameInput"),
  profileDesignationInput: document.querySelector("#profileDesignationInput"),
  profileDepartmentInput: document.querySelector("#profileDepartmentInput"),
  profileHouseTelInput: document.querySelector("#profileHouseTelInput"),
  profileOtherTelInput: document.querySelector("#profileOtherTelInput"),
  profileEvaluatorNameInput: document.querySelector("#profileEvaluatorNameInput"),
  profileEntitlementInput: document.querySelector("#profileEntitlementInput"),
  profileEmploymentTypeInput: document.querySelector("#profileEmploymentTypeInput"),
  profileEmploymentStartDateInput: document.querySelector("#profileEmploymentStartDateInput"),
  profileEmploymentEndDateInput: document.querySelector("#profileEmploymentEndDateInput"),
  profilePeriodReadout: document.querySelector("#profilePeriodReadout"),
  profileTakenReadout: document.querySelector("#profileTakenReadout"),
  profileBalanceReadout: document.querySelector("#profileBalanceReadout"),
  saveProfileButton: document.querySelector("#saveProfileButton"),
  profileMessage: document.querySelector("#profileMessage"),
  kpiTrackerTitle: document.querySelector("#kpiTrackerTitle"),
  kpiTrackerGrid: document.querySelector("#kpiTrackerGrid"),
  alForm: document.querySelector("#alForm"),
  startDateInput: document.querySelector("#startDateInput"),
  endDateInput: document.querySelector("#endDateInput"),
  leaveTypeInputs: document.querySelectorAll("input[name='leaveType']"),
  leaveReasonInput: document.querySelector("#leaveReasonInput"),
  durationValue: document.querySelector("#durationValue"),
  selectedLeaveTypeValue: document.querySelector("#selectedLeaveTypeValue"),
  balanceAfterLabel: document.querySelector("#balanceAfterLabel"),
  balanceAfterValue: document.querySelector("#balanceAfterValue"),
  generateButton: document.querySelector("#generateButton"),
  formMessage: document.querySelector("#formMessage"),
  halfDayCheckbox: document.querySelector("#halfDayCheckbox"),
  halfDayLabel: document.querySelector("#halfDayLabel"),
  halfDayPeriodGroup: document.querySelector("#halfDayPeriodGroup"),
  halfDayPeriodInputs: document.querySelectorAll("input[name='halfDayPeriod']"),
  removeEntitlementCheckbox: document.querySelector("#removeEntitlementCheckbox"),
  mcForm: document.querySelector("#mcForm"),
  mcStartDateInput: document.querySelector("#mcStartDateInput"),
  mcEndDateInput: document.querySelector("#mcEndDateInput"),
  mcReasonInput: document.querySelector("#mcReasonInput"),
  mcDurationValue: document.querySelector("#mcDurationValue"),
  mcGenerateButton: document.querySelector("#mcGenerateButton"),
  mcFormMessage: document.querySelector("#mcFormMessage"),
  kpiForm: document.querySelector("#kpiForm"),
  kpiMonthInput: document.querySelector("#kpiMonthInput"),
  kpiEvaluatorInput: document.querySelector("#kpiEvaluatorInput"),
  kpiTaskListInput: document.querySelector("#kpiTaskListInput"),
  kpiSectionsContainer: document.querySelector("#kpiSectionsContainer"),
  kpiOptionsContainer: document.querySelector("#kpiOptionsContainer"),
  kpiOverviewInstruction: document.querySelector("#kpiOverviewInstruction"),
  kpiSummaryInstruction: document.querySelector("#kpiSummaryInstruction"),
  kpiFeedbackInstruction: document.querySelector("#kpiFeedbackInstruction"),
  kpiStepLabel: document.querySelector("#kpiStepLabel"),
  kpiStepProgress: document.querySelector("#kpiStepProgress"),
  kpiPrevButton: document.querySelector("#kpiPrevButton"),
  kpiNextButton: document.querySelector("#kpiNextButton"),
  kpiWorkerFeedbackInput: document.querySelector("#kpiWorkerFeedbackInput"),
  kpiTrainingNeedsInput: document.querySelector("#kpiTrainingNeedsInput"),
  kpiEvaluatorFeedbackInput: document.querySelector("#kpiEvaluatorFeedbackInput"),
  kpiGenerateButton: document.querySelector("#kpiGenerateButton"),
  kpiFormMessage: document.querySelector("#kpiFormMessage"),
  expenseForm: document.querySelector("#expenseForm"),
  expenseMonthInput: document.querySelector("#expenseMonthInput"),
  expenseMonthEndInput: document.querySelector("#expenseMonthEndInput"),
  expenseSiteInput: document.querySelector("#expenseSiteInput"),
  expenseSupervisorInput: document.querySelector("#expenseSupervisorInput"),
  expenseAdvancesInput: document.querySelector("#expenseAdvancesInput"),
  expenseLinesBody: document.querySelector("#expenseLinesBody"),
  expenseAddLineButton: document.querySelector("#expenseAddLineButton"),
  expenseRemoveLineButton: document.querySelector("#expenseRemoveLineButton"),
  expenseLineCountValue: document.querySelector("#expenseLineCountValue"),
  expenseTotalValue: document.querySelector("#expenseTotalValue"),
  expenseReimburseValue: document.querySelector("#expenseReimburseValue"),
  expenseGenerateButton: document.querySelector("#expenseGenerateButton"),
  expenseFormMessage: document.querySelector("#expenseFormMessage"),
  otForm: document.querySelector("#otForm"),
  otMonthInput: document.querySelector("#otMonthInput"),
  otMonthEndInput: document.querySelector("#otMonthEndInput"),
  otLinesBody: document.querySelector("#otLinesBody"),
  otAddLineButton: document.querySelector("#otAddLineButton"),
  otRemoveLineButton: document.querySelector("#otRemoveLineButton"),
  otLineCountValue: document.querySelector("#otLineCountValue"),
  otTotalHoursValue: document.querySelector("#otTotalHoursValue"),
  otRateSplitValue: document.querySelector("#otRateSplitValue"),
  otGenerateButton: document.querySelector("#otGenerateButton"),
  otFormMessage: document.querySelector("#otFormMessage"),
  calendarTitle: document.querySelector("#calendarTitle"),
  calendarGrid: document.querySelector("#calendarGrid"),
  holidayList: document.querySelector("#holidayList"),
  previousMonthButton: document.querySelector("#previousMonthButton"),
  todayButton: document.querySelector("#todayButton"),
  nextMonthButton: document.querySelector("#nextMonthButton"),
  historyRows: document.querySelector("#historyRows"),
  historyMessage: document.querySelector("#historyMessage"),
  otherFormCards: document.querySelector("#otherFormCards"),
  otherPdfTitle: document.querySelector("#otherPdfTitle"),
  otherPdfOpenLink: document.querySelector("#otherPdfOpenLink"),
  otherPdfViewer: document.querySelector("#otherPdfViewer"),
  otherOnlyOfficeViewer: document.querySelector("#otherOnlyOfficeViewer"),
  otherViewerWrapper: document.querySelector("#otherViewerWrapper"),
  otherPreviewUnavailable: document.querySelector("#otherPreviewUnavailable"),
  otherPreviewOpenLink: document.querySelector("#otherPreviewOpenLink"),
  otherAdminPanel: document.querySelector("#otherAdminPanel"),
  otherUploadForm: document.querySelector("#otherUploadForm"),
  otherUploadInput: document.querySelector("#otherUploadInput"),
  otherUploadButton: document.querySelector("#otherUploadButton"),
  otherAdminRows: document.querySelector("#otherAdminRows"),
  otherAdminMessage: document.querySelector("#otherAdminMessage")
};

const profileSetupStandardFields = [
  { input: elements.setupNameInput, options: { isName: true } },
  { input: elements.setupDesignationInput },
  { input: elements.setupDepartmentInput },
  { input: elements.setupEvaluatorNameInput, options: { isName: true } }
];

const profileEditStandardFields = [
  { input: elements.profileNameInput, options: { isName: true } },
  { input: elements.profileDesignationInput },
  { input: elements.profileDepartmentInput },
  { input: elements.profileEvaluatorNameInput, options: { isName: true } }
];

function standardizeFieldGroup(fields) {
  fields.forEach(({ input, options }) => standardizeInputValue(input, options));
}

[...profileSetupStandardFields, ...profileEditStandardFields].forEach(({ input, options }) => {
  input?.addEventListener("blur", () => standardizeInputValue(input, options));
});

function todayIso() {
  const now = new Date();
  return toIsoDate(now);
}

function toIsoDate(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function parseIsoDate(value) {
  return new Date(`${value}T00:00:00`);
}

function formatDate(value) {
  if (!value) {
    return "-";
  }
  return parseIsoDate(value).toLocaleDateString(undefined, {
    day: "2-digit",
    month: "short",
    year: "numeric"
  });
}

function formatShortDate(value) {
  return parseIsoDate(value).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short"
  });
}

function monthInputValue(date = new Date()) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  return `${year}-${month}`;
}

function isWithinClaimMonthRange(itemDate, claimMonth, claimMonthEnd) {
  if (!itemDate || !claimMonth) {
    return false;
  }
  const start = claimMonth;
  const end = claimMonthEnd || claimMonth;
  if (end < start) {
    return false;
  }
  const itemMonth = itemDate.slice(0, 7);
  return itemMonth >= start && itemMonth <= end;
}

function formatMonthLabel(value) {
  if (!value) {
    return "-";
  }
  const [yearText, monthText] = value.split("-");
  const year = Number(yearText);
  const monthIndex = Number(monthText) - 1;
  return new Date(year, monthIndex, 1).toLocaleDateString(undefined, {
    month: "long",
    year: "numeric"
  });
}

function formatDays(value) {
  const number = Number(value || 0);
  return `${number} ${number === 1 ? "day" : "days"}`;
}

function formatCurrency(value) {
  return `RM ${Number(value || 0).toFixed(2)}`;
}

function getSelectedLeaveType() {
  const selected = document.querySelector("input[name='leaveType']:checked");
  return selected ? selected.value : "";
}

function getLeaveDisplay(item) {
  return item.leaveTypeLabel || item.formName || item.formType || "-";
}

function getSubmissionPeriodLabel(item) {
  if (item.periodLabel) {
    return item.periodLabel;
  }
  return `${formatDate(item.startDate)} to ${formatDate(item.endDate)}`;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, char => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "\"": "&quot;",
    "'": "&#39;"
  }[char]));
}

const profileNameParticles = new Set(["bin", "binti", "bt", "ibn", "al", "a/l", "a/p"]);
const profileTextAcronyms = new Set([
  "AL",
  "CEO",
  "CFO",
  "COO",
  "CTO",
  "DB",
  "EL",
  "HR",
  "HSE",
  "IT",
  "KPI",
  "MC",
  "PDF",
  "QA",
  "QC",
  "R&D",
  "SQL"
]);

function standardizeProfileToken(token, { isName = false, isFirst = false } = {}) {
  const lowerToken = String(token || "").toLowerCase();
  const upperToken = lowerToken.toUpperCase();
  if (isName && !isFirst && profileNameParticles.has(lowerToken)) {
    return lowerToken;
  }
  if (profileTextAcronyms.has(upperToken)) {
    return upperToken;
  }

  return lowerToken
    .split(/([-/'&])/)
    .map(part => {
      if (!part || "-/'&".includes(part)) {
        return part;
      }
      const upperPart = part.toUpperCase();
      if (profileTextAcronyms.has(upperPart)) {
        return upperPart;
      }
      return `${part.charAt(0).toUpperCase()}${part.slice(1)}`;
    })
    .join("");
}

function standardizeProfileText(value, options = {}) {
  const cleaned = String(value || "").trim().replace(/\s+/g, " ");
  if (!cleaned) {
    return "";
  }
  return cleaned
    .split(" ")
    .map((token, index) => standardizeProfileToken(token, {
      ...options,
      isFirst: index === 0
    }))
    .join(" ");
}

function standardizeInputValue(input, options = {}) {
  if (!input) {
    return "";
  }
  input.value = standardizeProfileText(input.value, options);
  return input.value;
}

function getExpenseMileageRate(transportMode) {
  return expenseTransportModes[transportMode]?.rate ?? expenseTransportModes.car.rate;
}

function getCalendarDisplayName(name, workerId = "", calendarName = "") {
  const override = String(calendarName || "").trim();
  if (override) {
    return override;
  }
  const parts = String(name || workerId || "").trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) {
    return "-";
  }

  const connectorIndex = parts.findIndex(part =>
    ["bin", "binti", "bt", "a/l", "a/p"].includes(part.toLowerCase())
  );
  if (connectorIndex > 0) {
    return parts[connectorIndex - 1];
  }

  return parts[0];
}

function getCalendarType(item) {
  if (item.formType === "MC") {
    return "MC";
  }
  if (item.formType === "EL" || item.leaveType === "emergency") {
    return "EL";
  }
  return "AL";
}

function setMessage(element, text, type = "") {
  element.textContent = text;
  element.className = `message ${type}`.trim();
}

function setButtonLoading(button, loading, loadingText) {
  if (!button) return;
  if (loading) {
    if (button.dataset.loading === "true") return;
    button.dataset.loading = "true";
    if (!button.dataset.originalText) button.dataset.originalText = button.textContent;
    button.disabled = true;
    button.textContent = "";
    const spinner = document.createElement("span");
    spinner.className = "button-spinner";
    button.appendChild(spinner);
    button.appendChild(document.createTextNode(loadingText || button.dataset.originalText));
  } else {
    if (button.dataset.loading !== "true") return;
    button.dataset.loading = "false";
    button.disabled = false;
    if (button.dataset.originalText) {
      button.textContent = button.dataset.originalText;
      delete button.dataset.originalText;
    }
  }
}

function renderThemeButtons() {
  const isDark = state.theme === "dark";
  elements.themeToggles.forEach(button => {
    button.textContent = isDark ? "Light mode" : "Dark mode";
    button.setAttribute("aria-label", isDark ? "Switch to light mode" : "Switch to dark mode");
    button.setAttribute("aria-pressed", String(isDark));
  });
}

function applyTheme(theme, options = {}) {
  const nextTheme = theme === "light" ? "light" : "dark";
  state.theme = nextTheme;
  document.documentElement.dataset.theme = nextTheme;
  if (options.persist !== false) {
    localStorage.setItem(themeStorageKey, nextTheme);
  }
  renderThemeButtons();
}

function toggleTheme() {
  applyTheme(state.theme === "dark" ? "light" : "dark");
}

function renderInstructionPanel(instruction) {
  return `
    <div class="instruction-panel">
      <strong>${escapeHtml(instruction.title)}</strong>
      <ul>
        ${instruction.lines.map(line => `<li>${escapeHtml(line)}</li>`).join("")}
      </ul>
    </div>
  `;
}

function renderKpiStaticInstructions() {
  elements.kpiOverviewInstruction.innerHTML = renderInstructionPanel(kpiStepInstructions.overview);
  elements.kpiSummaryInstruction.innerHTML = renderInstructionPanel(kpiStepInstructions.summary);
  elements.kpiFeedbackInstruction.innerHTML = renderInstructionPanel(kpiStepInstructions.feedback);
}

function renderKpiScoreChoices(sectionKey, index) {
  return [5, 4, 3, 2, 1]
    .map(score => {
      const id = `kpiScore-${sectionKey}-${index}-${score}`;
      return `
        <label class="kpi-score-choice" for="${id}">
          <input
            id="${id}"
            name="kpiScore-${sectionKey}-${index}"
            type="radio"
            value="${score}"
            data-kpi-score="${sectionKey}"
            data-kpi-score-index="${index}"
            required
          >
          <span>${score}</span>
        </label>
      `;
    })
    .join("");
}

function renderKpiSections() {
  elements.kpiSectionsContainer.innerHTML = kpiSections
    .map(section => `
      <section class="kpi-step kpi-section hidden" data-kpi-step="${section.key}">
        <div class="section-heading compact-heading">
          <div>
            <p class="eyebrow">Factor</p>
            <h2>${section.title}</h2>
          </div>
        </div>
        ${renderInstructionPanel(kpiScoreInstruction)}
        <div class="kpi-score-list">
          ${section.items
            .map((item, index) => `
              <div class="kpi-score-row">
                <div class="kpi-score-copy">${item}</div>
                <fieldset class="kpi-score-picker">
                  <legend>Score</legend>
                  <div class="kpi-score-choices">
                    ${renderKpiScoreChoices(section.key, index)}
                  </div>
                </fieldset>
              </div>
            `)
            .join("")}
        </div>
        <label>
          Comment
          <textarea data-kpi-comment="${section.key}" rows="3" placeholder="Optional section comment"></textarea>
        </label>
      </section>
    `)
    .join("");
}

function renderKpiOptions() {
  elements.kpiOptionsContainer.innerHTML = kpiOptionFields
    .map(field => `
      <label class="kpi-option-field">
        ${field.label}
        <span class="field-instruction">${escapeHtml(kpiOptionInstructions[field.key] || "")}</span>
        <select data-kpi-option="${field.key}" required>
          ${field.options.map(option => `<option value="${option}">${option}</option>`).join("")}
        </select>
      </label>
    `)
    .join("");
}

function renderFormAreas() {
  const selectedForm = state.selectedForm;
  elements.formCards.querySelectorAll("[data-form-id]").forEach(card => {
    card.classList.toggle("active", card.dataset.formId === selectedForm);
  });

  elements.formAreas.forEach(area => {
    area.classList.toggle("hidden", area.dataset.formArea !== selectedForm);
  });
}

function getOtherFormUrl(form) {
  return form.url || `/others/${encodeURIComponent(form.fileName)}`;
}

function renderOtherForms() {
  const selectedForm = state.otherForms[0];
  const isAdmin = state.worker?.role === "admin";
  elements.otherAdminPanel.classList.toggle("hidden", !isAdmin);

  if (!selectedForm) {
    elements.otherFormCards.innerHTML = "";
    elements.otherPdfTitle.textContent = "Viewer";
    elements.otherPdfOpenLink.removeAttribute("href");
    elements.otherPdfViewer.removeAttribute("src");
    elements.otherPdfViewer.classList.remove("hidden");
    elements.otherPreviewUnavailable.classList.add("hidden");
    destroyOnlyOfficeEditor();
    renderOtherAdminRows();
    return;
  }

  elements.otherFormCards.innerHTML = state.otherForms
    .map(form => {
      const badge = getOtherFormExtension(form).replace(/^\./, "").toUpperCase() || "FILE";
      return `
      <button
        class="form-card ready ${form.id === selectedForm.id ? "active" : ""}"
        type="button"
        data-other-form-id="${form.id}"
      >
        <strong>${escapeHtml(form.name)}</strong>
        <span>${escapeHtml(badge)}</span>
      </button>
    `;
    })
    .join("");
  selectOtherForm(selectedForm.id);
  renderOtherAdminRows();
}

const previewableExtensions = new Set([".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"]);
const onlyOfficeExtensions = new Set([".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".csv"]);

let onlyOfficeEditor = null;
let onlyOfficeApiPromise = null;
let onlyOfficeApiUrl = null;
let onlyOfficeRequestId = 0;

function destroyOnlyOfficeEditor() {
  onlyOfficeRequestId += 1;
  if (onlyOfficeEditor && typeof onlyOfficeEditor.destroyEditor === "function") {
    onlyOfficeEditor.destroyEditor();
  }
  onlyOfficeEditor = null;
  elements.otherOnlyOfficeViewer.innerHTML = "";
  elements.otherOnlyOfficeViewer.classList.add("hidden");
}

function loadOnlyOfficeApi(apiUrl) {
  if (window.DocsAPI && onlyOfficeApiUrl === apiUrl) {
    return Promise.resolve();
  }
  if (!onlyOfficeApiPromise || onlyOfficeApiUrl !== apiUrl) {
    onlyOfficeApiUrl = apiUrl;
    onlyOfficeApiPromise = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = apiUrl;
      script.onload = () => resolve();
      script.onerror = () => reject(new Error("Failed to load the ONLYOFFICE viewer."));
      document.head.appendChild(script);
    });
    onlyOfficeApiPromise.catch(() => {
      onlyOfficeApiPromise = null;
    });
  }
  return onlyOfficeApiPromise;
}

async function openOnlyOfficeViewer(selectedForm) {
  const requestId = ++onlyOfficeRequestId;
  const container = elements.otherOnlyOfficeViewer;
  container.classList.remove("hidden");
  try {
    const data = await api(`/api/others/${encodeURIComponent(selectedForm.fileName)}/viewer-config`);
    await loadOnlyOfficeApi(data.apiUrl);
    if (requestId !== onlyOfficeRequestId) {
      return;
    }
    const placeholder = document.createElement("div");
    placeholder.id = "otherOnlyOfficePlaceholder";
    container.innerHTML = "";
    container.appendChild(placeholder);
    onlyOfficeEditor = new DocsAPI.DocEditor(placeholder.id, data.config);
  } catch (error) {
    if (requestId !== onlyOfficeRequestId) {
      return;
    }
    container.innerHTML = "";
    container.classList.add("hidden");
    elements.otherPreviewUnavailable.classList.remove("hidden");
  }
}

function getOtherFormExtension(form) {
  const fileName = form?.fileName || "";
  const dotIndex = fileName.lastIndexOf(".");
  return dotIndex >= 0 ? fileName.slice(dotIndex).toLowerCase() : "";
}

function selectOtherForm(formId) {
  const selectedForm = state.otherForms.find(form => form.id === formId) || state.otherForms[0];
  if (!selectedForm) {
    return;
  }

  const fileUrl = getOtherFormUrl(selectedForm);
  const ext = getOtherFormExtension(selectedForm);
  const canPreview = previewableExtensions.has(ext);
  const canOnlyOffice = onlyOfficeExtensions.has(ext);

  elements.otherFormCards.querySelectorAll("[data-other-form-id]").forEach(card => {
    card.classList.toggle("active", card.dataset.otherFormId === selectedForm.id);
  });
  elements.otherPdfTitle.textContent = selectedForm.name;
  elements.otherPdfOpenLink.href = fileUrl;
  elements.otherPreviewOpenLink.href = fileUrl;

  destroyOnlyOfficeEditor();
  if (canPreview) {
    elements.otherPdfViewer.src = fileUrl;
    elements.otherPdfViewer.classList.remove("hidden");
    elements.otherPreviewUnavailable.classList.add("hidden");
  } else if (canOnlyOffice) {
    elements.otherPdfViewer.removeAttribute("src");
    elements.otherPdfViewer.classList.add("hidden");
    elements.otherPreviewUnavailable.classList.add("hidden");
    openOnlyOfficeViewer(selectedForm);
  } else {
    elements.otherPdfViewer.removeAttribute("src");
    elements.otherPdfViewer.classList.add("hidden");
    elements.otherPreviewUnavailable.classList.remove("hidden");
  }
}

function renderOtherAdminRows() {
  if (!elements.otherAdminRows) {
    return;
  }

  if (state.worker?.role !== "admin") {
    elements.otherAdminRows.innerHTML = "";
    setMessage(elements.otherAdminMessage, "");
    return;
  }

  if (state.otherForms.length === 0) {
    elements.otherAdminRows.innerHTML = "";
    return;
  }

  elements.otherAdminRows.innerHTML = state.otherForms
    .map(form => `
      <div class="other-admin-row">
        <span title="${escapeHtml(form.fileName)}">${escapeHtml(form.name)}</span>
        <button class="danger-button" type="button" data-delete-other-form="${escapeHtml(form.fileName)}">
          Remove
        </button>
      </div>
    `)
    .join("");
}

function getKpiStepTitle(stepKey) {
  if (stepKey === "overview") {
    return "Overview";
  }
  if (stepKey === "summary") {
    return "Summary";
  }
  if (stepKey === "feedback") {
    return "Feedback";
  }
  const section = kpiSections.find(item => item.key === stepKey);
  return section ? section.title : "KPI";
}

function isKpiOverviewComplete() {
  return Boolean(
    elements.kpiMonthInput.value &&
    elements.kpiEvaluatorInput.value.trim() &&
    elements.kpiTaskListInput.value.trim()
  );
}

function isKpiScoreSectionComplete(sectionKey) {
  const section = kpiSections.find(item => item.key === sectionKey);
  if (!section) {
    return true;
  }

  return section.items.every((_, index) =>
    Boolean(
      elements.kpiSectionsContainer.querySelector(
        `[data-kpi-score="${sectionKey}"][data-kpi-score-index="${index}"]:checked`
      )
    )
  );
}

function isKpiSummaryComplete() {
  return kpiOptionFields.every(field => {
    const input = elements.kpiOptionsContainer.querySelector(`[data-kpi-option="${field.key}"]`);
    return input && input.value && input.value !== "Pilih";
  });
}

function isKpiStepComplete(stepKey) {
  if (stepKey === "overview") {
    return isKpiOverviewComplete();
  }
  if (stepKey === "summary") {
    return isKpiSummaryComplete();
  }
  if (stepKey === "feedback") {
    return true;
  }
  return isKpiScoreSectionComplete(stepKey);
}

function getFirstIncompleteKpiStepIndex() {
  return kpiStepOrder.findIndex(stepKey => !isKpiStepComplete(stepKey));
}

function getIncompleteKpiStepIndexes() {
  return kpiStepOrder
    .map((stepKey, index) => (isKpiStepComplete(stepKey) ? null : index))
    .filter(index => index !== null);
}

function formatKpiStepNumbers(stepIndexes) {
  return stepIndexes.map(index => index + 1).join(", ");
}

function renderKpiStepProgress() {
  elements.kpiStepProgress.innerHTML = kpiStepOrder
    .map((stepKey, index) => {
      const stepNumber = index + 1;
      const stateClass = index < state.kpiStep ? "complete" : index === state.kpiStep ? "active" : "upcoming";
      const isIncomplete = state.kpiValidationAttempted && !isKpiStepComplete(stepKey);
      const validationClass = isIncomplete ? "incomplete" : "";
      const title = getKpiStepTitle(stepKey);
      const validationLabel = isIncomplete ? " incomplete" : "";
      return `
        <button
          class="kpi-step-marker ${stateClass} ${validationClass}"
          type="button"
          data-kpi-step-index="${index}"
          title="${escapeHtml(title)}"
          aria-label="Go to step ${stepNumber}: ${escapeHtml(title)}${validationLabel}"
          aria-invalid="${isIncomplete ? "true" : "false"}"
          ${index === state.kpiStep ? 'aria-current="step"' : ""}
        >
          <span>${stepNumber}</span>
        </button>
      `;
    })
    .join("");
}

function renderKpiWizard() {
  const currentStep = kpiStepOrder[state.kpiStep] || "overview";
  elements.kpiStepLabel.textContent = `${state.kpiStep + 1}/${kpiStepOrder.length} ${getKpiStepTitle(currentStep)}`;
  renderKpiStepProgress();
  document.querySelectorAll("[data-kpi-step]").forEach(step => {
    step.classList.toggle("hidden", step.dataset.kpiStep !== currentStep);
  });
  elements.kpiPrevButton.disabled = state.kpiStep === 0;
  const isLast = state.kpiStep === kpiStepOrder.length - 1;
  elements.kpiNextButton.classList.toggle("hidden", isLast);
  elements.kpiGenerateButton.classList.toggle("hidden", !isLast);
}

async function api(path, options = {}) {
  const authHeaders = state.token ? { "authorization": `Bearer ${state.token}` } : {};
  const headers = {
    ...authHeaders,
    ...(options.headers || {})
  };
  if (!(options.body instanceof FormData) && !headers["content-type"] && !headers["Content-Type"]) {
    headers["content-type"] = "application/json";
  }
  const response = await fetch(path, {
    headers,
    ...options
  });

  const payload = await response.json().catch(() => ({}));

  if (response.status === 401) {
    clearAuth();
    showView("login");
    throw new Error(payload.error || "Session expired. Please log in again.");
  }

  if (!response.ok) {
    throw new Error(payload.error || "Request failed.");
  }

  return payload;
}

function clearAuth() {
  state.token = null;
  state.worker = null;
  state.submissions = [];
  state.otherForms = [];
  localStorage.removeItem("token");
  state.draftsRestored = false;
}

function showView(view) {
  elements.loginView.classList.toggle("hidden", view !== "login");
  elements.registerView.classList.toggle("hidden", view !== "register");
  elements.profileSetupView.classList.toggle("hidden", view !== "profileSetup");
  elements.workspaceView.classList.toggle("hidden", view !== "workspace");

  if (view === "profileSetup") {
    updateSetupEmploymentDateFields();
  }
}

async function refreshWorkerProfile(options = {}) {
  const { resetDates = false } = options;
  const { worker } = await api(`/api/workers/${encodeURIComponent(state.worker.workerId)}`);
  state.worker = worker;
  renderWorker({ resetDates });
}

function inclusiveDayCount(startDate, endDate) {
  const oneDay = 24 * 60 * 60 * 1000;
  return Math.round((endDate.getTime() - startDate.getTime()) / oneDay) + 1;
}

function calculateAl() {
  const startValue = elements.startDateInput.value;
  const endValue = elements.endDateInput.value || startValue;

  if (!startValue || !endValue || !state.worker) {
    return null;
  }

  const start = parseIsoDate(startValue);
  const end = parseIsoDate(endValue);

  if (end < start) {
    elements.durationValue.textContent = "Invalid range";
    elements.balanceAfterValue.textContent = "-";
    return null;
  }

  const isHalfDay = startValue === endValue && elements.halfDayCheckbox.checked;
  const halfDayPeriod = isHalfDay ? getSelectedHalfDayPeriod() : null;
  const rawDays = inclusiveDayCount(start, end);
  const durationDays = isHalfDay ? 0.5 : rawDays;
  const balanceBefore = Number(state.worker.annualLeaveBalance || 0);
  const leaveType = getSelectedLeaveType();
  const affectsAnnualLeave = alDeductingLeaveTypes.has(leaveType);
  const balanceAfter = affectsAnnualLeave ? Math.max(balanceBefore - durationDays, 0) : balanceBefore;

  elements.durationValue.textContent = durationDays === 0.5 ? "0.5 day" : `${durationDays} ${durationDays === 1 ? "day" : "days"}`;
  elements.balanceAfterLabel.textContent = affectsAnnualLeave ? "AL balance after" : "AL balance";
  elements.balanceAfterValue.textContent = affectsAnnualLeave ? `${balanceAfter} days` : `${balanceBefore} days (unchanged)`;
  elements.selectedLeaveTypeValue.textContent = leaveTypeLabels[leaveType] || "-";

  return {
    startDate: startValue,
    endDate: endValue,
    durationDays,
    leaveType,
    affectsAnnualLeave,
    balanceAfter,
    isHalfDay,
    halfDayPeriod
  };
}

function getSelectedHalfDayPeriod() {
  for (const input of elements.halfDayPeriodInputs) {
    if (input.checked) return input.value;
  }
  return "AM";
}

function calculateMc() {
  const startValue = elements.mcStartDateInput.value;
  const endValue = elements.mcEndDateInput.value || startValue;

  if (!startValue || !endValue) {
    return null;
  }

  const start = parseIsoDate(startValue);
  const end = parseIsoDate(endValue);

  if (end < start) {
    elements.mcDurationValue.textContent = "Invalid range";
    return null;
  }

  const durationDays = inclusiveDayCount(start, end);
  elements.mcDurationValue.textContent = `${durationDays} ${durationDays === 1 ? "day" : "days"}`;

  return {
    startDate: startValue,
    endDate: endValue,
    durationDays
  };
}

function renderExpenseInput(rowIndex, column) {
  const label = expenseColumnLabels[column.key];
  const commonAttributes = `
    data-expense-row="${rowIndex}"
    data-expense-field="${column.key}"
    aria-label="${escapeHtml(label)}"
  `;
  let control = "";
  if (column.type === "select") {
    control = `
      <select ${commonAttributes}>
        ${Object.entries(expenseTransportModes).map(([value, mode]) => `
          <option value="${value}" ${value === "car" ? "selected" : ""}>${escapeHtml(mode.label)}</option>
        `).join("")}
      </select>
    `;
  } else if (column.type === "textarea") {
    control = `
      <textarea
        ${commonAttributes}
        class="expense-description-input"
        rows="1"
        ${column.placeholder ? `placeholder="${escapeHtml(column.placeholder)}"` : ""}
      ></textarea>
    `;
  } else {
    control = `
      <input
        ${commonAttributes}
        type="${column.type}"
        ${column.type === "number" ? `min="0" step="${column.step}"` : ""}
        ${column.placeholder ? `placeholder="${escapeHtml(column.placeholder)}"` : ""}
      >
    `;
  }

  return `
    <label class="expense-field expense-field-${column.key}">
      <span>${label}</span>
      ${control}
    </label>
  `;
}

function renderExpenseHeader() {
  return `
    <div class="expense-sheet-row expense-sheet-header" aria-hidden="true">
      <div>#</div>
      ${expenseColumns.map(column => `<div>${escapeHtml(expenseColumnLabels[column.key])}</div>`).join("")}
    </div>
  `;
}

function renderExpenseRow(rowIndex) {
  return `
    <section class="expense-sheet-row expense-line-card" data-expense-line="${rowIndex}" aria-label="Expense row ${rowIndex + 1}">
      <div class="expense-line-title">
        <strong>${rowIndex + 1}</strong>
      </div>
      ${expenseColumns.map(column => renderExpenseInput(rowIndex, column)).join("")}
    </section>
  `;
}

function updateExpenseLineControls() {
  const lineCount = elements.expenseLinesBody.querySelectorAll("[data-expense-line]").length;
  elements.expenseAddLineButton.disabled = lineCount >= expenseMaxLineCount;
  elements.expenseAddLineButton.textContent = lineCount >= expenseMaxLineCount ? "Max rows" : "+ Add row";
  elements.expenseRemoveLineButton.disabled = lineCount <= expenseMinLineCount;
}

function renderExpenseRows() {
  elements.expenseLinesBody.innerHTML = renderExpenseHeader() + Array.from(
    { length: expenseInitialLineCount },
    (_, rowIndex) => renderExpenseRow(rowIndex)
  ).join("");
  updateExpenseLineControls();
  resizeExpenseDescriptions();
}

function addExpenseRow() {
  const lineCount = elements.expenseLinesBody.querySelectorAll("[data-expense-line]").length;
  if (lineCount >= expenseMaxLineCount) {
    return;
  }
  elements.expenseLinesBody.insertAdjacentHTML("beforeend", renderExpenseRow(lineCount));
  updateExpenseLineControls();
  resizeExpenseDescriptions(elements.expenseLinesBody.querySelector(`[data-expense-line="${lineCount}"]`));
  calculateExpenses();
}

function removeExpenseRow() {
  const lineCount = elements.expenseLinesBody.querySelectorAll("[data-expense-line]").length;
  if (lineCount <= expenseMinLineCount) {
    return;
  }

  elements.expenseLinesBody.querySelector(`[data-expense-line="${lineCount - 1}"]`)?.remove();
  updateExpenseLineControls();
  calculateExpenses();
}

function getExpenseLineInputs(rowIndex) {
  return [...elements.expenseLinesBody.querySelectorAll(`[data-expense-row="${rowIndex}"]`)];
}

function resizeExpenseDescription(textarea) {
  textarea.style.height = "auto";
  textarea.style.height = `${Math.max(textarea.scrollHeight, 34)}px`;
}

function resizeExpenseDescriptions(scope = elements.expenseLinesBody) {
  scope.querySelectorAll(".expense-description-input").forEach(resizeExpenseDescription);
}

function collectExpenseItems() {
  const items = [];
  const lineCount = elements.expenseLinesBody.querySelectorAll("[data-expense-line]").length;
  for (let rowIndex = 0; rowIndex < lineCount; rowIndex += 1) {
    const inputs = getExpenseLineInputs(rowIndex);
    const item = {};
    inputs.forEach(input => {
      item[input.dataset.expenseField] = input.value.trim();
    });
    if (!expenseTransportModes[item.transportMode]) {
      item.transportMode = "car";
    }

    const hasText = Boolean(item.date || item.description || item.project);
    const hasAmount = expenseAmountFields.some(field => Number(item[field] || 0) > 0);
    if (!hasText && !hasAmount) {
      continue;
    }
    items.push(item);
  }
  return items;
}

function calculateExpenses() {
  const items = collectExpenseItems();
  const advances = Number(elements.expenseAdvancesInput.value || 0);
  const totalAmount = items.reduce((sum, item) => {
    const mileage = Number(item.totalKm || 0) * getExpenseMileageRate(item.transportMode);
    const directAmount = expenseAmountFields
      .filter(field => field !== "totalKm")
      .reduce((amountSum, field) => amountSum + Number(item[field] || 0), 0);
    return sum + mileage + directAmount;
  }, 0);

  elements.expenseLineCountValue.textContent = `${items.length} ${items.length === 1 ? "line" : "lines"}`;
  elements.expenseTotalValue.textContent = formatCurrency(totalAmount);
  elements.expenseReimburseValue.textContent = formatCurrency(totalAmount - advances);

  if (!elements.expenseMonthInput.value || items.length === 0) {
    return null;
  }

  return {
    claimMonth: elements.expenseMonthInput.value,
    claimMonthEnd: elements.expenseMonthEndInput.value || null,
    site: elements.expenseSiteInput.value.trim(),
    supervisorName: elements.expenseSupervisorInput.value.trim(),
    advances,
    items
  };
}

function renderOtInput(rowIndex, column) {
  const label = otColumnLabels[column.key];
  const commonAttributes = `
    data-ot-row="${rowIndex}"
    data-ot-field="${column.key}"
    aria-label="${escapeHtml(label)}"
  `;
  let control = "";
  if (column.type === "select") {
    control = `
      <select ${commonAttributes}>
        ${Object.entries(otRateTypes).map(([value, rate]) => `
          <option value="${value}" ${value === "normal" ? "selected" : ""}>${escapeHtml(rate.label)}</option>
        `).join("")}
      </select>
    `;
  } else if (column.type === "textarea") {
    control = `
      <textarea
        ${commonAttributes}
        class="expense-description-input"
        rows="1"
        ${column.placeholder ? `placeholder="${escapeHtml(column.placeholder)}"` : ""}
      ></textarea>
    `;
  } else if (column.type === "readonly") {
    control = `<input ${commonAttributes} type="text" readonly tabindex="-1">`;
  } else {
    control = `
      <input
        ${commonAttributes}
        type="${column.type}"
        ${column.key === "timeFrom" || column.key === "timeTo" ? `inputmode="numeric" maxlength="4" pattern="([01][0-9]|2[0-3])[0-5][0-9]"` : ""}
        ${column.placeholder ? `placeholder="${escapeHtml(column.placeholder)}"` : ""}
      >
    `;
  }

  return `
    <label class="expense-field expense-field-${column.key}">
      <span>${label}</span>
      ${control}
    </label>
  `;
}

function renderOtHeader() {
  return `
    <div class="expense-sheet-row ot-sheet-row expense-sheet-header" aria-hidden="true">
      <div>#</div>
      ${otColumns.map(column => `<div>${escapeHtml(otColumnLabels[column.key])}</div>`).join("")}
    </div>
  `;
}

function renderOtRow(rowIndex) {
  return `
    <section class="expense-sheet-row ot-sheet-row expense-line-card" data-ot-line="${rowIndex}" aria-label="Overtime row ${rowIndex + 1}">
      <div class="expense-line-title">
        <strong>${rowIndex + 1}</strong>
      </div>
      ${otColumns.map(column => renderOtInput(rowIndex, column)).join("")}
    </section>
  `;
}

function updateOtLineControls() {
  const lineCount = elements.otLinesBody.querySelectorAll("[data-ot-line]").length;
  elements.otAddLineButton.disabled = lineCount >= otMaxLineCount;
  elements.otAddLineButton.textContent = lineCount >= otMaxLineCount ? "Max rows" : "+ Add row";
  elements.otRemoveLineButton.disabled = lineCount <= otMinLineCount;
}

function renderOtRows() {
  elements.otLinesBody.innerHTML = renderOtHeader() + Array.from(
    { length: otInitialLineCount },
    (_, rowIndex) => renderOtRow(rowIndex)
  ).join("");
  updateOtLineControls();
  resizeExpenseDescriptions(elements.otLinesBody);
}

function addOtRow() {
  const lineCount = elements.otLinesBody.querySelectorAll("[data-ot-line]").length;
  if (lineCount >= otMaxLineCount) {
    return;
  }
  elements.otLinesBody.insertAdjacentHTML("beforeend", renderOtRow(lineCount));
  updateOtLineControls();
  resizeExpenseDescriptions(elements.otLinesBody.querySelector(`[data-ot-line="${lineCount}"]`));
  calculateOt();
}

function removeOtRow() {
  const lineCount = elements.otLinesBody.querySelectorAll("[data-ot-line]").length;
  if (lineCount <= otMinLineCount) {
    return;
  }

  elements.otLinesBody.querySelector(`[data-ot-line="${lineCount - 1}"]`)?.remove();
  updateOtLineControls();
  calculateOt();
}

function isValidOtTime(value) {
  return /^([01]\d|2[0-3])[0-5]\d$/.test(value);
}

function computeOtHours(timeFrom, timeTo) {
  if (!isValidOtTime(timeFrom) || !isValidOtTime(timeTo) || timeFrom === timeTo) {
    return null;
  }
  const startMinutes = Number(timeFrom.slice(0, 2)) * 60 + Number(timeFrom.slice(2));
  const endMinutes = Number(timeTo.slice(0, 2)) * 60 + Number(timeTo.slice(2));
  let minutes = endMinutes - startMinutes;
  if (minutes <= 0) {
    minutes += 24 * 60;
  }
  return Math.round((minutes / 60) * 100) / 100;
}

function collectOtItems() {
  const items = [];
  const lineCount = elements.otLinesBody.querySelectorAll("[data-ot-line]").length;
  for (let rowIndex = 0; rowIndex < lineCount; rowIndex += 1) {
    const inputs = [...elements.otLinesBody.querySelectorAll(`[data-ot-row="${rowIndex}"]`)];
    const item = {};
    inputs.forEach(input => {
      item[input.dataset.otField] = input.value.trim();
    });
    if (!otRateTypes[item.rateType]) {
      item.rateType = "normal";
    }

    if (!item.date && !item.timeFrom && !item.timeTo && !item.description) {
      continue;
    }
    item.hours = computeOtHours(item.timeFrom, item.timeTo);
    items.push(item);
  }
  return items;
}

function calculateOt() {
  const items = collectOtItems();

  const lineCount = elements.otLinesBody.querySelectorAll("[data-ot-line]").length;
  for (let rowIndex = 0; rowIndex < lineCount; rowIndex += 1) {
    const hoursInput = elements.otLinesBody.querySelector(`[data-ot-row="${rowIndex}"][data-ot-field="hours"]`);
    const timeFrom = elements.otLinesBody.querySelector(`[data-ot-row="${rowIndex}"][data-ot-field="timeFrom"]`)?.value.trim() || "";
    const timeTo = elements.otLinesBody.querySelector(`[data-ot-row="${rowIndex}"][data-ot-field="timeTo"]`)?.value.trim() || "";
    if (hoursInput) {
      const hours = computeOtHours(timeFrom, timeTo);
      hoursInput.value = hours === null ? "" : String(hours);
    }
  }

  const totalHours = items.reduce((sum, item) => sum + (item.hours || 0), 0);
  const rateHours = { normal: 0, rest: 0, holiday: 0 };
  items.forEach(item => {
    rateHours[item.rateType] += item.hours || 0;
  });

  elements.otLineCountValue.textContent = `${items.length} ${items.length === 1 ? "line" : "lines"}`;
  elements.otTotalHoursValue.textContent = `${Math.round(totalHours * 100) / 100} h`;
  elements.otRateSplitValue.textContent = `${Math.round(rateHours.normal * 100) / 100} / ${Math.round(rateHours.rest * 100) / 100} / ${Math.round(rateHours.holiday * 100) / 100}`;

  if (!elements.otMonthInput.value || items.length === 0) {
    return null;
  }

  return {
    claimMonth: elements.otMonthInput.value,
    claimMonthEnd: elements.otMonthEndInput.value || null,
    items
  };
}

function collectKpiScores() {
  const scores = {};
  for (const section of kpiSections) {
    scores[section.key] = section.items.map((_, index) => {
      const input = elements.kpiSectionsContainer.querySelector(
        `[data-kpi-score="${section.key}"][data-kpi-score-index="${index}"]:checked`
      );
      return Number(input?.value || 0);
    });
  }
  return scores;
}

function collectKpiComments() {
  const comments = {};
  for (const section of kpiSections) {
    const input = elements.kpiSectionsContainer.querySelector(`[data-kpi-comment="${section.key}"]`);
    comments[section.key] = input.value.trim();
  }
  return comments;
}

function collectKpiOptions() {
  const summaryOptions = {};
  for (const field of kpiOptionFields) {
    const input = elements.kpiOptionsContainer.querySelector(`[data-kpi-option="${field.key}"]`);
    summaryOptions[field.key] = input.value;
  }
  return summaryOptions;
}

function calculateKpi() {
  const kpiMonth = elements.kpiMonthInput.value;
  if (!kpiMonth) {
    return null;
  }

  const scores = collectKpiScores();
  for (const section of kpiSections) {
    if (scores[section.key].some(score => score < 1 || score > 5)) {
      return null;
    }
  }

  const summaryOptions = collectKpiOptions();
  if (Object.values(summaryOptions).some(value => !value || value === "Pilih")) {
    return null;
  }

  return {
    kpiMonth,
    scores,
    comments: collectKpiComments(),
    summaryOptions
  };
}

async function login(workerId, password) {
  setMessage(elements.loginMessage, "Logging in...");
  const { token, worker } = await api("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ workerId, password })
  });
  state.token = token;
  state.worker = worker;
  localStorage.setItem("token", token);

  if (!worker.profileComplete) {
    showView("profileSetup");
    return;
  }

  showView("workspace");
  renderWorker();
  await loadForms();
  await loadOtherForms();
  await loadSubmissions();
}

async function register(workerId, password) {
  setMessage(elements.registerMessage, "Creating account...");
  const { token, worker } = await api("/api/auth/register", {
    method: "POST",
    body: JSON.stringify({ workerId, password })
  });
  state.token = token;
  state.worker = worker;
  localStorage.setItem("token", token);
  showView("profileSetup");
}

function logout() {
  clearAuth();
  showView("login");
  setMessage(elements.loginMessage, "");
}

async function enterWorkspace() {
  showView("workspace");
  renderWorker();
  await loadForms();
  await loadOtherForms();
  await loadSubmissions();
}

function renderWorker(options = {}) {
  const { resetDates = true } = options;
  const worker = state.worker;
  elements.workerName.textContent = worker.name || worker.workerId;
  elements.workerIdBadge.textContent = worker.workerId;
  elements.workerDesignation.textContent = worker.role === "admin"
    ? `${worker.designation || "No designation"} | Admin`
    : worker.designation || "No designation";
  elements.profileName.textContent = worker.name || "-";
  elements.profileDesignation.textContent = worker.designation || "-";
  elements.profileHouseTel.textContent = worker.houseTel || "-";
  elements.profileOtherPhone.textContent = worker.otherTel || "-";
  elements.profileBalance.textContent = formatDays(worker.annualLeaveBalance);
  renderWorkerFieldCopies();
  renderProfileForm();

  if (resetDates) {
    const today = todayIso();
    elements.startDateInput.value = today;
    elements.endDateInput.value = today;
    elements.mcStartDateInput.value = today;
    elements.mcEndDateInput.value = today;
    elements.kpiMonthInput.value = monthInputValue();
    elements.expenseMonthInput.value = monthInputValue();
    elements.expenseMonthEndInput.value = "";
    elements.otMonthInput.value = monthInputValue();
    elements.otMonthEndInput.value = "";
  }
  calculateAl();
  toggleHalfDayVisibility();
  calculateMc();
  renderKpiForm();
  renderExpenseForm();
  renderOtForm();
  renderFormAreas();
  if (!state.draftsRestored) {
    state.draftsRestored = true;
    restoreAllDrafts();
  }
}

function renderWorkerFieldCopies() {
  const worker = state.worker;
  const values = {
    name: worker.name || "-",
    designation: worker.designation || "-",
    department: worker.department || "-",
    houseTel: worker.houseTel || "-",
    otherTel: worker.otherTel || "-",
    workerId: worker.workerId || "-",
    evaluatorName: worker.evaluatorName || "-"
  };

  document.querySelectorAll("[data-worker-field]").forEach(element => {
    element.textContent = values[element.dataset.workerField] || "-";
  });
}

function renderProfileForm() {
  const worker = state.worker;
  elements.profileWorkerIdInput.value = worker.workerId || "";
  elements.profileNameInput.value = worker.name || "";
  elements.profileDesignationInput.value = worker.designation || "";
  elements.profileDepartmentInput.value = worker.department || "";
  elements.profileHouseTelInput.value = worker.houseTel || "";
  elements.profileOtherTelInput.value = worker.otherTel || "";
  elements.profileEvaluatorNameInput.value = worker.evaluatorName || "";
  elements.profileCalendarNameInput.value = worker.calendarName || "";
  elements.profileEntitlementInput.value = worker.annualLeaveEntitlement ?? 0;
  elements.profileEmploymentTypeInput.value = worker.employmentType || "permanent";
  elements.profileEmploymentStartDateInput.value = worker.employmentStartDate || "";
  elements.profileEmploymentEndDateInput.value = worker.employmentEndDate || "";
  updateEmploymentDateFields();
  elements.profilePeriodReadout.textContent = `${formatDate(worker.employmentStartDate)} to ${formatDate(worker.employmentEndDate)}`;
  elements.profileTakenReadout.textContent = formatDays(worker.annualLeaveTaken);
  elements.profileBalanceReadout.textContent = formatDays(worker.annualLeaveBalance);
  renderKpiTracker();
}

function renderKpiForm() {
  if (!state.worker) {
    return;
  }
  if (!elements.kpiMonthInput.value) {
    elements.kpiMonthInput.value = monthInputValue();
  }
  elements.kpiEvaluatorInput.value = state.worker.evaluatorName || "";
  renderKpiWizard();
}

function renderExpenseForm() {
  if (!state.worker) {
    return;
  }
  if (!elements.expenseMonthInput.value) {
    elements.expenseMonthInput.value = monthInputValue();
  }
  if (!elements.expenseSupervisorInput.value) {
    elements.expenseSupervisorInput.value = state.worker.evaluatorName || "";
  }
  calculateExpenses();
}

function renderOtForm() {
  if (!state.worker) {
    return;
  }
  if (!elements.otMonthInput.value) {
    elements.otMonthInput.value = monthInputValue();
  }
  calculateOt();
}

function renderKpiTracker() {
  const year = new Date().getFullYear();
  elements.kpiTrackerTitle.textContent = `Monthly KPI Status ${year}`;

  const monthlyEntries = new Map(
    state.submissions
      .filter(item => item.formType === "KPI" && Number(item.kpiYear) === year)
      .map(item => [item.kpiMonth, item])
  );

  elements.kpiTrackerGrid.innerHTML = Array.from({ length: 12 }, (_, index) => {
    const month = String(index + 1).padStart(2, "0");
    const monthKey = `${year}-${month}`;
    const item = monthlyEntries.get(monthKey);
    const label = new Date(year, index, 1).toLocaleDateString(undefined, { month: "short" });
    return `
      <div class="kpi-tracker-card ${item ? "complete" : "pending"}">
        <strong>${label}</strong>
        <span>${item ? "Submitted" : "Pending"}</span>
        ${item ? `<a href="${item.pdfUrl}" target="_blank" rel="noreferrer">Open PDF</a>` : "<span>Not submitted</span>"}
      </div>
    `;
  }).join("");
}

function getCurrentYearBounds() {
  const year = new Date().getFullYear();
  return {
    start: `${year}-01-01`,
    end: `${year}-12-31`
  };
}

function updateSetupEmploymentDateFields() {
  const isPermanent = elements.setupEmploymentTypeInput.value === "permanent";

  if (isPermanent) {
    const bounds = getCurrentYearBounds();
    elements.setupEmploymentStartDateInput.value = bounds.start;
    elements.setupEmploymentEndDateInput.value = bounds.end;
  }

  elements.setupEmploymentStartDateInput.disabled = isPermanent;
  elements.setupEmploymentEndDateInput.disabled = isPermanent;
}

function updateEmploymentDateFields() {
  const isPermanent = elements.profileEmploymentTypeInput.value === "permanent";

  if (isPermanent) {
    const bounds = getCurrentYearBounds();
    elements.profileEmploymentStartDateInput.value = bounds.start;
    elements.profileEmploymentEndDateInput.value = bounds.end;
  }

  elements.profileEmploymentStartDateInput.readOnly = isPermanent;
  elements.profileEmploymentEndDateInput.readOnly = isPermanent;
}

async function loadForms() {
  const { forms } = await api("/api/forms");
  if (!forms.some(form => form.id === state.selectedForm && form.status === "ready")) {
    const firstReady = forms.find(form => form.status === "ready");
    state.selectedForm = firstReady ? firstReady.id : "AL";
  }
  elements.formCards.innerHTML = forms
    .map(form => {
      const ready = form.status === "ready";
      return `
        <button
          class="form-card ${ready ? "ready" : "disabled"} ${state.selectedForm === form.id ? "active" : ""}"
          type="button"
          data-form-id="${form.id}"
          ${ready ? "" : "disabled"}
        >
          <strong>${form.name}</strong>
          <span>${form.id}</span>
        </button>
      `;
    })
    .join("");
  renderFormAreas();
}

async function loadOtherForms() {
  const { forms } = await api("/api/others");
  state.otherForms = forms || [];
  renderOtherForms();
}

function selectForm(formId) {
  state.selectedForm = formId;
  renderFormAreas();
}

async function loadSubmissions() {
  if (!state.worker) {
    return;
  }

  const [{ submissions }, { entries }] = await Promise.all([
    api("/api/submissions"),
    api("/api/calendar")
  ]);
  state.submissions = submissions;
  state.calendarEntries = entries;
  renderKpiTracker();
  renderHistory();
  renderCalendar();
}

function renderHistory() {
  if (state.submissions.length === 0) {
    elements.historyRows.innerHTML = `
      <tr>
        <td colspan="7">No generated PDFs yet.</td>
      </tr>
    `;
    return;
  }

  elements.historyRows.innerHTML = state.submissions
    .map(item => `
      <tr>
        <td>${item.formType}</td>
        <td>${getLeaveDisplay(item)}</td>
        <td>${getSubmissionPeriodLabel(item)}</td>
        <td>${item.durationDays}</td>
        <td>${new Date(item.createdAt).toLocaleString()}</td>
        <td><a href="${item.pdfUrl}" target="_blank" rel="noreferrer">Download</a></td>
        <td>
          <button class="print-button" type="button" data-print-submission="${item.id}">Print</button>
          <button class="edit-button" type="button" data-edit-submission="${item.id}">Edit</button>
          <button class="danger-button" type="button" data-delete-submission="${item.id}">
            Delete
          </button>
        </td>

      </tr>
    `)
    .join("");
}

function renderCalendar() {
  const monthDate = state.calendarDate;
  const year = monthDate.getFullYear();
  const month = monthDate.getMonth();

  elements.calendarTitle.textContent = monthDate.toLocaleDateString(undefined, {
    month: "long",
    year: "numeric"
  });

  const firstOfMonth = new Date(year, month, 1);
  const start = new Date(year, month, 1 - firstOfMonth.getDay());
  const days = [];

  for (let index = 0; index < 42; index += 1) {
    days.push(new Date(start.getFullYear(), start.getMonth(), start.getDate() + index));
  }

  elements.calendarGrid.innerHTML = days
    .map(day => {
      const dayIso = toIsoDate(day);
      const outside = day.getMonth() !== month;
      const isToday = dayIso === todayIso();
      const holiday = companyHolidayByDate.get(dayIso);
      const dayClasses = [
        "calendar-day",
        outside ? "outside" : "",
        holiday ? "holiday" : "",
        isToday ? "today" : ""
      ].filter(Boolean).join(" ");
      const entries = state.calendarEntries.filter(item => {
        const entryStart = parseIsoDate(item.calendarStart || item.startDate);
        const entryEnd = parseIsoDate(item.calendarEnd || item.endDate);
        return day >= entryStart && day <= entryEnd;
      });

      return `
        <div class="${dayClasses}"${isToday ? ' aria-current="date"' : ""}>
          <div class="calendar-date-row">
            <div class="calendar-date-group">
              <div class="calendar-date">${day.getDate()}</div>
            </div>
            ${holiday ? `
              <span class="calendar-holiday-marker" tabindex="0" aria-label="Holiday: ${escapeHtml(holiday.name)}">
                Cuti
                <span class="calendar-holiday-tooltip" role="tooltip">
                  ${escapeHtml(holiday.name)}
                </span>
              </span>
            ` : ""}
          </div>
          ${entries
            .map(item => {
              const type = getCalendarType(item);
              const displayName = getCalendarDisplayName(item.workerName, item.workerId, item.calendarName);
              const title = `${item.workerName || item.workerId} - ${calendarTypeLabels[type]}`;
              const tag = item.pdfUrl ? "a" : "span";
              const hrefAttr = item.pdfUrl
                ? ` href="${item.pdfUrl}" target="_blank" rel="noreferrer"`
                : "";
              return `
                <${tag} class="calendar-entry ${type.toLowerCase()}${item.pdfUrl ? " has-pdf" : ""}" title="${escapeHtml(title)}"${hrefAttr}>
                  ${escapeHtml(displayName)}
                </${tag}>
              `;
            })
            .join("")}
        </div>
      `;
    })
    .join("");
}

function renderUpcomingHolidays() {
  if (!elements.holidayList) {
    return;
  }

  const today = todayIso();
  const upcomingHolidays = companyHolidays.filter(holiday => holiday.date >= today);

  if (upcomingHolidays.length === 0) {
    elements.holidayList.innerHTML = `
      <li class="holiday-empty">
        <span>No more holidays listed for this year.</span>
      </li>
    `;
    return;
  }

  elements.holidayList.innerHTML = upcomingHolidays
    .map(holiday => `
      <li>
        <time datetime="${holiday.date}">${formatShortDate(holiday.date)}</time>
        <span>${escapeHtml(holiday.name)}</span>
      </li>
    `)
    .join("");
}

function setActiveTab(panelId) {
  elements.tabs.forEach(tab => {
    tab.classList.toggle("active", tab.dataset.tab === panelId);
  });
  elements.panels.forEach(panel => {
    panel.classList.toggle("active-panel", panel.id === panelId);
  });
}

elements.loginForm.addEventListener("submit", async event => {
  event.preventDefault();
  const workerId = elements.workerIdInput.value.trim();
  const password = elements.loginPasswordInput.value;
  if (!workerId) {
    setMessage(elements.loginMessage, "Worker ID is required.", "error");
    return;
  }
  if (!password) {
    setMessage(elements.loginMessage, "Password is required.", "error");
    return;
  }
  try {
    await login(workerId, password);
  } catch (error) {
    setMessage(elements.loginMessage, error.message, "error");
  }
});

elements.showRegisterButton.addEventListener("click", () => {
  setMessage(elements.loginMessage, "");
  showView("register");
});

elements.showLoginButton.addEventListener("click", () => {
  setMessage(elements.registerMessage, "");
  showView("login");
});

elements.registerForm.addEventListener("submit", async event => {
  event.preventDefault();
  const workerId = elements.registerWorkerIdInput.value.trim();
  const password = elements.registerPasswordInput.value;
  if (!workerId) {
    setMessage(elements.registerMessage, "Worker ID is required.", "error");
    return;
  }
  if (!password) {
    setMessage(elements.registerMessage, "Password is required.", "error");
    return;
  }
  try {
    await register(workerId, password);
  } catch (error) {
    setMessage(elements.registerMessage, error.message, "error");
  }
});

elements.profileSetupForm.addEventListener("submit", async event => {
  event.preventDefault();
  if (!state.worker) return;

  setButtonLoading(elements.saveProfileSetupButton, true, "Saving...");
  setMessage(elements.profileSetupMessage, "Saving profile...");

  try {
    standardizeFieldGroup(profileSetupStandardFields);
    const payload = {
      name: elements.setupNameInput.value,
      calendarName: elements.setupCalendarNameInput.value,
      designation: elements.setupDesignationInput.value,
      department: elements.setupDepartmentInput.value,
      houseTel: elements.setupHouseTelInput.value,
      otherTel: elements.setupOtherTelInput.value,
      evaluatorName: elements.setupEvaluatorNameInput.value,
      annualLeaveEntitlement: elements.setupEntitlementInput.value,
      employmentType: elements.setupEmploymentTypeInput.value,
      employmentStartDate: elements.setupEmploymentStartDateInput.value,
      employmentEndDate: elements.setupEmploymentEndDateInput.value
    };
    const { worker } = await api(`/api/workers/${encodeURIComponent(state.worker.workerId)}`, {
      method: "PUT",
      body: JSON.stringify(payload)
    });
    state.worker = worker;
    await enterWorkspace();
  } catch (error) {
    setMessage(elements.profileSetupMessage, error.message, "error");
  } finally {
    setButtonLoading(elements.saveProfileSetupButton, false);
  }
});

elements.setupEmploymentTypeInput.addEventListener("change", updateSetupEmploymentDateFields);

elements.logoutButton.addEventListener("click", logout);

elements.themeToggles.forEach(button => {
  button.addEventListener("click", toggleTheme);
});

elements.tabs.forEach(tab => {
  tab.addEventListener("click", () => setActiveTab(tab.dataset.tab));
});

function toggleHalfDayVisibility() {
  const show = elements.startDateInput.value === elements.endDateInput.value
    && !!elements.startDateInput.value;
  elements.halfDayLabel.style.display = show ? "" : "none";
  elements.halfDayPeriodGroup.style.display = show && elements.halfDayCheckbox.checked ? "" : "none";
  if (!show) elements.halfDayCheckbox.checked = false;
}

elements.startDateInput.addEventListener("change", () => {
  if (!elements.endDateInput.value || elements.endDateInput.value < elements.startDateInput.value) {
    elements.endDateInput.value = elements.startDateInput.value;
  }
  toggleHalfDayVisibility();
  calculateAl();
});

elements.endDateInput.addEventListener("change", () => {
  toggleHalfDayVisibility();
  calculateAl();
});

elements.halfDayCheckbox.addEventListener("change", () => {
  elements.halfDayPeriodGroup.style.display = elements.halfDayCheckbox.checked ? "" : "none";
  calculateAl();
});

elements.leaveTypeInputs.forEach(input => {
  input.addEventListener("change", calculateAl);
});

elements.formCards.addEventListener("click", event => {
  const button = event.target.closest("[data-form-id]");
  if (!button || button.disabled) {
    return;
  }
  selectForm(button.dataset.formId);
});

elements.otherFormCards.addEventListener("click", event => {
  const button = event.target.closest("[data-other-form-id]");
  if (!button) {
    return;
  }
  selectOtherForm(button.dataset.otherFormId);
});

elements.otherUploadForm.addEventListener("submit", async event => {
  event.preventDefault();

  if (state.worker?.role !== "admin") {
    setMessage(elements.otherAdminMessage, "Admin access required.", "error");
    return;
  }

  const file = elements.otherUploadInput.files[0];
  if (!file) {
    setMessage(elements.otherAdminMessage, "Choose a PDF file.", "error");
    return;
  }

  setButtonLoading(elements.otherUploadButton, true, "Uploading...");
  setMessage(elements.otherAdminMessage, "Uploading PDF...");

  try {
    const formData = new FormData();
    formData.append("file", file);
    const { forms } = await api("/api/admin/others", {
      method: "POST",
      body: formData
    });
    state.otherForms = forms || [];
    elements.otherUploadForm.reset();
    renderOtherForms();
    setMessage(elements.otherAdminMessage, "PDF uploaded.", "success");
  } catch (error) {
    setMessage(elements.otherAdminMessage, error.message, "error");
  } finally {
    setButtonLoading(elements.otherUploadButton, false);
  }
});

elements.otherAdminRows.addEventListener("click", async event => {
  const button = event.target.closest("[data-delete-other-form]");
  if (!button || state.worker?.role !== "admin") {
    return;
  }

  const fileName = button.dataset.deleteOtherForm;
  const confirmed = window.confirm(`Remove ${fileName}?`);
  if (!confirmed) {
    return;
  }

  setButtonLoading(button, true, "Removing...");
  setMessage(elements.otherAdminMessage, "Removing PDF...");

  try {
    const { forms } = await api(`/api/admin/others/${encodeURIComponent(fileName)}`, {
      method: "DELETE"
    });
    state.otherForms = forms || [];
    renderOtherForms();
    setMessage(elements.otherAdminMessage, "PDF removed.", "success");
  } catch (error) {
    setMessage(elements.otherAdminMessage, error.message, "error");
    setButtonLoading(button, false);
  }
});

elements.alForm.addEventListener("submit", async event => {
  event.preventDefault();
  const calculation = calculateAl();
  const reason = elements.leaveReasonInput.value.trim();

  if (!calculation) {
    setMessage(elements.formMessage, "Choose a valid AL date range.", "error");
    return;
  }

  if (!calculation.leaveType) {
    setMessage(elements.formMessage, "Select one leave type.", "error");
    return;
  }

  if (!reason) {
    setMessage(elements.formMessage, "Reason is required.", "error");
    return;
  }

  setButtonLoading(elements.generateButton, true, "Generating...");
  setMessage(elements.formMessage, "Generating PDF and syncing spreadsheet...");

  try {
    const payload = {
      workerId: state.worker.workerId,
      startDate: calculation.startDate,
      endDate: calculation.endDate,
      leaveType: calculation.leaveType,
      isHalfDay: calculation.isHalfDay || false,
      halfDayPeriod: calculation.halfDayPeriod,
      removeEntitlement: elements.removeEntitlementCheckbox.checked,
      reason
    };
    const editing = isEditingForm("al");
    const { submission } = await api(
      editing ? submissionEditEndpoint() : "/api/submissions/al",
      { method: editing ? "PUT" : "POST", body: JSON.stringify(payload) }
    );
    setMessage(
      elements.formMessage,
      editing ? `Updated: ${submission.pdfFileName}` : `PDF generated: ${submission.pdfFileName}`,
      "success"
    );
    drafts.al.clear();
    clearEditAfterSubmit("al");
    await refreshWorkerProfile({ resetDates: false });
    await loadSubmissions();
    window.open(submission.pdfUrl, "_blank", "noreferrer");
  } catch (error) {
    setMessage(elements.formMessage, error.message, "error");
  } finally {
    setButtonLoading(elements.generateButton, false);
  }
});

elements.mcStartDateInput.addEventListener("change", () => {
  if (!elements.mcEndDateInput.value || elements.mcEndDateInput.value < elements.mcStartDateInput.value) {
    elements.mcEndDateInput.value = elements.mcStartDateInput.value;
  }
  calculateMc();
});

elements.mcEndDateInput.addEventListener("change", calculateMc);

elements.mcForm.addEventListener("submit", async event => {
  event.preventDefault();
  const calculation = calculateMc();
  const sicknessReason = elements.mcReasonInput.value.trim();

  if (!calculation) {
    setMessage(elements.mcFormMessage, "Choose a valid MC date range.", "error");
    return;
  }

  if (!sicknessReason) {
    setMessage(elements.mcFormMessage, "Sickness/reason is required.", "error");
    return;
  }

  setButtonLoading(elements.mcGenerateButton, true, "Generating...");
  setMessage(elements.mcFormMessage, "Generating PDF and syncing spreadsheet...");

  try {
    const payload = {
      workerId: state.worker.workerId,
      startDate: calculation.startDate,
      endDate: calculation.endDate,
      sicknessReason
    };
    const editing = isEditingForm("mc");
    const { submission } = await api(
      editing ? submissionEditEndpoint() : "/api/submissions/mc",
      { method: editing ? "PUT" : "POST", body: JSON.stringify(payload) }
    );
    setMessage(
      elements.mcFormMessage,
      editing ? `Updated: ${submission.pdfFileName}` : `PDF generated: ${submission.pdfFileName}`,
      "success"
    );
    drafts.mc.clear();
    clearEditAfterSubmit("mc");
    await loadSubmissions();
    window.open(submission.pdfUrl, "_blank", "noreferrer");
  } catch (error) {
    setMessage(elements.mcFormMessage, error.message, "error");
  } finally {
    setButtonLoading(elements.mcGenerateButton, false);
  }
});

elements.kpiPrevButton.addEventListener("click", () => {
  state.kpiStep = Math.max(state.kpiStep - 1, 0);
  renderKpiWizard();
});

elements.kpiStepProgress.addEventListener("click", event => {
  const marker = event.target.closest("[data-kpi-step-index]");
  if (!marker) {
    return;
  }

  state.kpiStep = Number(marker.dataset.kpiStepIndex);
  renderKpiWizard();
});

elements.kpiNextButton.addEventListener("click", () => {
  state.kpiStep = Math.min(state.kpiStep + 1, kpiStepOrder.length - 1);
  renderKpiWizard();
});

elements.kpiForm.addEventListener("input", () => {
  if (state.kpiValidationAttempted) {
    renderKpiStepProgress();
  }
});

elements.kpiForm.addEventListener("change", () => {
  if (state.kpiValidationAttempted) {
    renderKpiStepProgress();
  }
});

elements.kpiForm.addEventListener("submit", async event => {
  event.preventDefault();
  const calculation = calculateKpi();
  const evaluatorName = elements.kpiEvaluatorInput.value.trim();
  const taskList = elements.kpiTaskListInput.value.trim();
  const incompleteSteps = getIncompleteKpiStepIndexes();
  const firstIncompleteStep = incompleteSteps[0] ?? -1;

  if (firstIncompleteStep !== -1 || !calculation) {
    state.kpiValidationAttempted = true;
    state.kpiStep = firstIncompleteStep === -1 ? state.kpiStep : firstIncompleteStep;
    renderKpiWizard();
    const incompleteStepText = incompleteSteps.length
      ? ` Review red step ${incompleteSteps.length === 1 ? "number" : "numbers"} ${formatKpiStepNumbers(incompleteSteps)}.`
      : "";
    setMessage(
      elements.kpiFormMessage,
      `Complete the evaluator, task list, KPI month, all 1-5 scores, and all summary selections.${incompleteStepText}`,
      "error"
    );
    return;
  }

  setButtonLoading(elements.kpiGenerateButton, true, "Generating...");
  setMessage(elements.kpiFormMessage, "Generating PDF...");

  try {
    const payload = {
      workerId: state.worker.workerId,
      kpiMonth: calculation.kpiMonth,
      evaluatorName,
      taskList,
      scores: calculation.scores,
      comments: calculation.comments,
      summaryOptions: calculation.summaryOptions,
      workerFeedback: elements.kpiWorkerFeedbackInput.value.trim(),
      trainingNeeds: elements.kpiTrainingNeedsInput.value.trim(),
      evaluatorFeedback: elements.kpiEvaluatorFeedbackInput.value.trim()
    };
    const editing = isEditingForm("kpi");
    const { submission } = await api(
      editing ? submissionEditEndpoint() : "/api/submissions/kpi",
      { method: editing ? "PUT" : "POST", body: JSON.stringify(payload) }
    );
    setMessage(
      elements.kpiFormMessage,
      editing ? `Updated: ${submission.pdfFileName}` : `PDF generated: ${submission.pdfFileName}`,
      "success"
    );
    drafts.kpi.clear();
    clearEditAfterSubmit("kpi");
    state.kpiValidationAttempted = false;
    renderKpiWizard();
    await loadSubmissions();
    window.open(submission.pdfUrl, "_blank", "noreferrer");
  } catch (error) {
    setMessage(elements.kpiFormMessage, error.message, "error");
  } finally {
    setButtonLoading(elements.kpiGenerateButton, false);
  }
});

elements.expenseForm.addEventListener("input", event => {
  if (event.target.classList.contains("expense-description-input")) {
    resizeExpenseDescription(event.target);
  }
  calculateExpenses();
});
elements.expenseForm.addEventListener("change", calculateExpenses);
elements.expenseAddLineButton.addEventListener("click", addExpenseRow);
elements.expenseRemoveLineButton.addEventListener("click", removeExpenseRow);

elements.expenseForm.addEventListener("submit", async event => {
  event.preventDefault();
  const calculation = calculateExpenses();

  if (!calculation) {
    setMessage(elements.expenseFormMessage, "Choose a claim month and add at least one expense line.", "error");
    return;
  }

  if (!calculation.supervisorName) {
    setMessage(elements.expenseFormMessage, "Supervisor name is required.", "error");
    return;
  }

  const invalidLine = calculation.items.find(item => !item.date || !item.description);
  if (invalidLine) {
    setMessage(elements.expenseFormMessage, "Every expense line needs a date and description.", "error");
    return;
  }

  if (calculation.claimMonthEnd && calculation.claimMonthEnd < calculation.claimMonth) {
    setMessage(elements.expenseFormMessage, "Claim month end cannot be before the start month.", "error");
    return;
  }

  const outsideMonth = calculation.items.find(item => !isWithinClaimMonthRange(item.date, calculation.claimMonth, calculation.claimMonthEnd));
  if (outsideMonth) {
    setMessage(elements.expenseFormMessage, "Expense dates must fall within the claim month range.", "error");
    return;
  }

  setButtonLoading(elements.expenseGenerateButton, true, "Generating...");
  setMessage(elements.expenseFormMessage, "Generating PDF...");

  try {
    const editing = isEditingForm("expense");
    const { submission } = await api(
      editing ? submissionEditEndpoint() : "/api/submissions/expenses",
      { method: editing ? "PUT" : "POST", body: JSON.stringify(calculation) }
    );
    setMessage(
      elements.expenseFormMessage,
      editing ? `Updated: ${submission.pdfFileName}` : `PDF generated: ${submission.pdfFileName}`,
      "success"
    );
    drafts.expense.clear();
    clearEditAfterSubmit("expense");
    await loadSubmissions();
    window.open(submission.pdfUrl, "_blank", "noreferrer");
  } catch (error) {
    setMessage(elements.expenseFormMessage, error.message, "error");
  } finally {
    setButtonLoading(elements.expenseGenerateButton, false);
  }
});

elements.otForm.addEventListener("input", event => {
  if (event.target.classList.contains("expense-description-input")) {
    resizeExpenseDescription(event.target);
  }
  calculateOt();
});
elements.otForm.addEventListener("change", calculateOt);
elements.otAddLineButton.addEventListener("click", addOtRow);
elements.otRemoveLineButton.addEventListener("click", removeOtRow);

elements.otForm.addEventListener("submit", async event => {
  event.preventDefault();
  const calculation = calculateOt();

  if (!calculation) {
    setMessage(elements.otFormMessage, "Choose a claim month and add at least one overtime line.", "error");
    return;
  }

  const invalidLine = calculation.items.find(item => !item.date || !item.description);
  if (invalidLine) {
    setMessage(elements.otFormMessage, "Every overtime line needs a date and description.", "error");
    return;
  }

  const invalidTime = calculation.items.find(item => item.hours === null);
  if (invalidTime) {
    setMessage(elements.otFormMessage, "Times must use 24-hour HHMM format (e.g. 1800 to 2200).", "error");
    return;
  }

  if (calculation.claimMonthEnd && calculation.claimMonthEnd < calculation.claimMonth) {
    setMessage(elements.otFormMessage, "Claim month end cannot be before the start month.", "error");
    return;
  }

  const outsideMonth = calculation.items.find(item => !isWithinClaimMonthRange(item.date, calculation.claimMonth, calculation.claimMonthEnd));
  if (outsideMonth) {
    setMessage(elements.otFormMessage, "Overtime dates must fall within the claim month range.", "error");
    return;
  }

  setButtonLoading(elements.otGenerateButton, true, "Generating...");
  setMessage(elements.otFormMessage, "Generating PDF...");

  try {
    const editing = isEditingForm("ot");
    const { submission } = await api(
      editing ? submissionEditEndpoint() : "/api/submissions/ot",
      { method: editing ? "PUT" : "POST", body: JSON.stringify(calculation) }
    );
    setMessage(
      elements.otFormMessage,
      editing ? `Updated: ${submission.pdfFileName}` : `PDF generated: ${submission.pdfFileName}`,
      "success"
    );
    drafts.ot.clear();
    clearEditAfterSubmit("ot");
    await loadSubmissions();
    window.open(submission.pdfUrl, "_blank", "noreferrer");
  } catch (error) {
    setMessage(elements.otFormMessage, error.message, "error");
  } finally {
    setButtonLoading(elements.otGenerateButton, false);
  }
});

elements.profileForm.addEventListener("submit", async event => {
  event.preventDefault();

  if (!state.worker) {
    return;
  }

  setButtonLoading(elements.saveProfileButton, true, "Saving...");
  setMessage(elements.profileMessage, "Saving profile and syncing spreadsheet...");

  try {
    standardizeFieldGroup(profileEditStandardFields);
    const payload = {
      name: elements.profileNameInput.value,
      calendarName: elements.profileCalendarNameInput.value,
      designation: elements.profileDesignationInput.value,
      department: elements.profileDepartmentInput.value,
      houseTel: elements.profileHouseTelInput.value,
      otherTel: elements.profileOtherTelInput.value,
      evaluatorName: elements.profileEvaluatorNameInput.value,
      annualLeaveEntitlement: elements.profileEntitlementInput.value,
      employmentType: elements.profileEmploymentTypeInput.value,
      employmentStartDate: elements.profileEmploymentStartDateInput.value,
      employmentEndDate: elements.profileEmploymentEndDateInput.value
    };
    const { worker } = await api(`/api/workers/${encodeURIComponent(state.worker.workerId)}`, {
      method: "PUT",
      body: JSON.stringify(payload)
    });

    state.worker = worker;
    renderWorker({ resetDates: false });
    setMessage(elements.profileMessage, "Profile saved.", "success");
  } catch (error) {
    setMessage(elements.profileMessage, error.message, "error");
  } finally {
    setButtonLoading(elements.saveProfileButton, false);
  }
});

elements.profileEmploymentTypeInput.addEventListener("change", updateEmploymentDateFields);

elements.historyRows.addEventListener("click", async event => {
  const printButton = event.target.closest("[data-print-submission]");
  if (printButton) {
    const submissionId = printButton.dataset.printSubmission;
    setButtonLoading(printButton, true, "Printing...");
    setMessage(elements.historyMessage, "Sending document to office printer...");

    try {
      const response = await api(`/api/submissions/${encodeURIComponent(submissionId)}/print`, {
        method: "POST"
      });
      setMessage(elements.historyMessage, response.message || "Sent to printer successfully.", "success");
    } catch (error) {
      setMessage(elements.historyMessage, error.message || "Failed to print document.", "error");
    } finally {
      setButtonLoading(printButton, false);
    }
    return;
  }

  const editButton = event.target.closest("[data-edit-submission]");

  if (editButton) {
    const submission = state.submissions.find(item => item.id === editButton.dataset.editSubmission);
    if (submission) startEdit(submission);
    return;
  }
  const button = event.target.closest("[data-delete-submission]");
  if (!button || !state.worker) {
    return;
  }
  cancelEdit();

  const submissionId = button.dataset.deleteSubmission;
  const submission = state.submissions.find(item => item.id === submissionId);
  const isCalendarForm = submission && ["AL", "EL", "MC"].includes(submission.formType);
  const confirmMessage = isCalendarForm
    ? "This will delete the request, remove its generated files, and remove its entry from the shared spreadsheet calendar."
    : "This will delete the request and remove its generated files.";
  const confirmed = await confirmDialog({
    title: "Delete request?",
    message: confirmMessage,
    confirmLabel: "Delete",
    cancelLabel: "Cancel",
    danger: true
  });
  if (!confirmed) {
    return;
  }

  setButtonLoading(button, true, "Deleting...");
  setMessage(elements.historyMessage, "Deleting request and updating spreadsheet...");

  try {
    await api(`/api/submissions/${encodeURIComponent(submissionId)}`, {
      method: "DELETE"
    });
    await refreshWorkerProfile({ resetDates: false });
    await loadSubmissions();
    setMessage(elements.historyMessage, "Request deleted and generated files removed.", "success");
  } catch (error) {
    setMessage(elements.historyMessage, error.message, "error");
    setButtonLoading(button, false);
  }
});

elements.previousMonthButton.addEventListener("click", () => {
  state.calendarDate = new Date(
    state.calendarDate.getFullYear(),
    state.calendarDate.getMonth() - 1,
    1
  );
  renderCalendar();
});

elements.nextMonthButton.addEventListener("click", () => {
  state.calendarDate = new Date(
    state.calendarDate.getFullYear(),
    state.calendarDate.getMonth() + 1,
    1
  );
  renderCalendar();
});

elements.todayButton.addEventListener("click", () => {
  state.calendarDate = new Date();
  renderCalendar();
});

// ----- Form draft persistence (localStorage, per worker) -----
const DRAFT_PREFIX = "officeFormDraft.";

function draftStorageKey(formKey) {
  return state.worker ? `${DRAFT_PREFIX}${state.worker.workerId}.${formKey}` : null;
}

function saveDraft(formKey, data) {
  const key = draftStorageKey(formKey);
  if (!key) return;
  try { localStorage.setItem(key, JSON.stringify(data)); } catch (e) { /* ignore quota */ }
}

function loadDraftObj(formKey) {
  const key = draftStorageKey(formKey);
  if (!key) return null;
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : null;
  } catch (e) { return null; }
}

function removeDraft(formKey) {
  const key = draftStorageKey(formKey);
  if (!key) return;
  try { localStorage.removeItem(key); } catch (e) {}
}

const draftSaveTimers = {};
function scheduleDraftSave(formKey, serialize) {
  clearTimeout(draftSaveTimers[formKey]);
  draftSaveTimers[formKey] = setTimeout(() => saveDraft(formKey, serialize()), 400);
}

function serializeAlDraft() {
  const start = elements.startDateInput.value;
  const end = elements.endDateInput.value;
  const lt = document.querySelector("input[name='leaveType']:checked");
  const period = document.querySelector("input[name='halfDayPeriod']:checked");
  return {
    startDate: start,
    endDate: end,
    leaveType: lt ? lt.value : "annual",
    reason: elements.leaveReasonInput.value,
    halfDay: start && start === end ? elements.halfDayCheckbox.checked : false,
    halfDayPeriod: period ? period.value : "AM",
    removeEntitlement: elements.removeEntitlementCheckbox.checked
  };
}

function restoreAlDraft(d) {
  if (!d) return;
  if (d.startDate) elements.startDateInput.value = d.startDate;
  if (d.endDate) elements.endDateInput.value = d.endDate;
  const lt = document.querySelector(`input[name='leaveType'][value='${d.leaveType || "annual"}']`);
  if (lt) lt.checked = true;
  if (typeof d.reason === "string") elements.leaveReasonInput.value = d.reason;
  const canHalfDay = elements.startDateInput.value && elements.startDateInput.value === elements.endDateInput.value;
  elements.halfDayCheckbox.checked = canHalfDay && !!d.halfDay;
  const period = document.querySelector(`input[name='halfDayPeriod'][value='${d.halfDayPeriod || "AM"}']`);
  if (period) period.checked = true;
  elements.removeEntitlementCheckbox.checked = !!d.removeEntitlement;
  toggleHalfDayVisibility();
  calculateAl();
}

function serializeMcDraft() {
  return {
    startDate: elements.mcStartDateInput.value,
    endDate: elements.mcEndDateInput.value,
    reason: elements.mcReasonInput.value
  };
}

function restoreMcDraft(d) {
  if (!d) return;
  if (d.startDate) elements.mcStartDateInput.value = d.startDate;
  if (d.endDate) elements.mcEndDateInput.value = d.endDate;
  if (typeof d.reason === "string") elements.mcReasonInput.value = d.reason;
  calculateMc();
}

function serializeKpiDraft() {
  const scores = {};
  kpiSections.forEach(section => {
    section.items.forEach((_, index) => {
      const checked = document.querySelector(`[data-kpi-score='${section.key}'][data-kpi-score-index='${index}']:checked`);
      if (checked) scores[`${section.key}-${index}`] = Number(checked.value);
    });
  });
  const comments = {};
  kpiSections.forEach(section => {
    const ta = document.querySelector(`[data-kpi-comment='${section.key}']`);
    if (ta) comments[section.key] = ta.value;
  });
  const options = {};
  kpiOptionFields.forEach(field => {
    const sel = document.querySelector(`[data-kpi-option='${field.key}']`);
    if (sel) options[field.key] = sel.value;
  });
  return {
    month: elements.kpiMonthInput.value,
    evaluatorName: elements.kpiEvaluatorInput.value,
    taskList: elements.kpiTaskListInput.value,
    workerFeedback: elements.kpiWorkerFeedbackInput.value,
    trainingNeeds: elements.kpiTrainingNeedsInput.value,
    evaluatorFeedback: elements.kpiEvaluatorFeedbackInput.value,
    scores,
    comments,
    options,
    step: state.kpiStep
  };
}

function restoreKpiDraft(d) {
  if (!d) return;
  if (d.month) elements.kpiMonthInput.value = d.month;
  if (typeof d.evaluatorName === "string") elements.kpiEvaluatorInput.value = d.evaluatorName;
  if (typeof d.taskList === "string") elements.kpiTaskListInput.value = d.taskList;
  if (typeof d.workerFeedback === "string") elements.kpiWorkerFeedbackInput.value = d.workerFeedback;
  if (typeof d.trainingNeeds === "string") elements.kpiTrainingNeedsInput.value = d.trainingNeeds;
  if (typeof d.evaluatorFeedback === "string") elements.kpiEvaluatorFeedbackInput.value = d.evaluatorFeedback;
  if (d.scores) {
    Object.entries(d.scores).forEach(([key, value]) => {
      const [sectionKey, indexStr] = key.split("-");
      const radio = document.querySelector(`[data-kpi-score='${sectionKey}'][data-kpi-score-index='${indexStr}'][value='${value}']`);
      if (radio) radio.checked = true;
    });
  }
  if (d.comments) {
    Object.entries(d.comments).forEach(([sectionKey, value]) => {
      const ta = document.querySelector(`[data-kpi-comment='${sectionKey}']`);
      if (ta) ta.value = value;
    });
  }
  if (d.options) {
    Object.entries(d.options).forEach(([fieldKey, value]) => {
      const sel = document.querySelector(`[data-kpi-option='${fieldKey}']`);
      if (sel) sel.value = value;
    });
  }
  if (typeof d.step === "number" && d.step >= 0 && d.step < kpiStepOrder.length) {
    state.kpiStep = d.step;
  }
  renderKpiWizard();
}

function serializeExpenseDraft() {
  const lineCount = elements.expenseLinesBody.querySelectorAll("[data-expense-line]").length;
  const rows = [];
  for (let i = 0; i < lineCount; i += 1) {
    const row = {};
    expenseColumns.forEach(col => {
      const input = elements.expenseLinesBody.querySelector(`[data-expense-row='${i}'][data-expense-field='${col.key}']`);
      if (input) row[col.key] = input.value;
    });
    rows.push(row);
  }
  return {
    month: elements.expenseMonthInput.value,
    monthEnd: elements.expenseMonthEndInput.value,
    site: elements.expenseSiteInput.value,
    supervisorName: elements.expenseSupervisorInput.value,
    advances: elements.expenseAdvancesInput.value,
    rows
  };
}

function restoreExpenseDraft(d) {
  if (!d) return;
  if (d.month) elements.expenseMonthInput.value = d.month;
  if (typeof d.monthEnd === "string") elements.expenseMonthEndInput.value = d.monthEnd;
  if (typeof d.site === "string") elements.expenseSiteInput.value = d.site;
  if (typeof d.supervisorName === "string") elements.expenseSupervisorInput.value = d.supervisorName;
  if (typeof d.advances === "string") elements.expenseAdvancesInput.value = d.advances;
  if (Array.isArray(d.rows)) {
    while (elements.expenseLinesBody.querySelectorAll("[data-expense-line]").length < d.rows.length) {
      addExpenseRow();
    }
    d.rows.forEach((row, i) => {
      if (!row) return;
      expenseColumns.forEach(col => {
        const input = elements.expenseLinesBody.querySelector(`[data-expense-row='${i}'][data-expense-field='${col.key}']`);
        if (input && typeof row[col.key] === "string") input.value = row[col.key];
      });
    });
  }
  resizeExpenseDescriptions();
  calculateExpenses();
}

function serializeOtDraft() {
  const lineCount = elements.otLinesBody.querySelectorAll("[data-ot-line]").length;
  const rows = [];
  for (let i = 0; i < lineCount; i += 1) {
    const row = {};
    otColumns.forEach(col => {
      if (col.key === "hours") return;
      const input = elements.otLinesBody.querySelector(`[data-ot-row='${i}'][data-ot-field='${col.key}']`);
      if (input) row[col.key] = input.value;
    });
    rows.push(row);
  }
  return {
    month: elements.otMonthInput.value,
    monthEnd: elements.otMonthEndInput.value,
    rows
  };
}

function restoreOtDraft(d) {
  if (!d) return;
  if (d.month) elements.otMonthInput.value = d.month;
  if (typeof d.monthEnd === "string") elements.otMonthEndInput.value = d.monthEnd;
  if (Array.isArray(d.rows)) {
    while (elements.otLinesBody.querySelectorAll("[data-ot-line]").length < d.rows.length) {
      addOtRow();
    }
    d.rows.forEach((row, i) => {
      if (!row) return;
      otColumns.forEach(col => {
        if (col.key === "hours") return;
        const input = elements.otLinesBody.querySelector(`[data-ot-row='${i}'][data-ot-field='${col.key}']`);
        if (input && typeof row[col.key] === "string") input.value = row[col.key];
      });
    });
  }
  resizeExpenseDescriptions(elements.otLinesBody);
  calculateOt();
}

const drafts = {
  al: { serialize: serializeAlDraft, restore: restoreAlDraft, clear: () => removeDraft("al") },
  mc: { serialize: serializeMcDraft, restore: restoreMcDraft, clear: () => removeDraft("mc") },
  kpi: { serialize: serializeKpiDraft, restore: restoreKpiDraft, clear: () => removeDraft("kpi") },
  expense: { serialize: serializeExpenseDraft, restore: restoreExpenseDraft, clear: () => removeDraft("expense") },
  ot: { serialize: serializeOtDraft, restore: restoreOtDraft, clear: () => removeDraft("ot") }
};

function restoreAllDrafts() {
  Object.keys(drafts).forEach(key => {
    const data = loadDraftObj(key);
    if (data) drafts[key].restore(data);
  });
}

[
  [elements.alForm, "al"],
  [elements.mcForm, "mc"],
  [elements.kpiForm, "kpi"],
  [elements.expenseForm, "expense"],
  [elements.otForm, "ot"]
].forEach(([formEl, key]) => {
  if (!formEl) return;
  formEl.addEventListener("input", () => scheduleDraftSave(key, drafts[key].serialize));
  formEl.addEventListener("change", () => scheduleDraftSave(key, drafts[key].serialize));
});

// ----- Patch notes: fetch latest merged PRs from GitHub once per hour -----
const PATCHNOTES_CACHE_KEY = "patchnotesCache_v2";
const PATCHNOTES_TTL_MS = 60 * 60 * 1000;

function formatPrDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function renderPatchnotes(items, listEl) {
  if (!listEl) return;
  listEl.innerHTML = "";
  items.forEach(item => {
    const li = document.createElement("li");
    const a = document.createElement("a");
    a.className = "patchnote-item";
    a.href = item.html_url;
    a.target = "_blank";
    a.rel = "noopener noreferrer";

    const badge = document.createElement("span");
    badge.className = "patchnote-badge";
    badge.textContent = `PR #${item.number}`;

    const title = document.createElement("span");
    title.className = "patchnote-title";
    title.textContent = item.title;

    const date = document.createElement("span");
    date.className = "patchnote-date";
    date.textContent = formatPrDate(item.merged_at || item.updated_at);

    a.appendChild(badge);
    a.appendChild(title);
    a.appendChild(date);
    li.appendChild(a);
    listEl.appendChild(li);
  });
}

async function loadPatchnotes() {
  const listEl = document.getElementById("patchnotesList");
  if (!listEl) return;
  const repo = listEl.dataset.repo || "mrl-hzq/officeForm";

  let cache = null;
  try {
    const raw = localStorage.getItem(PATCHNOTES_CACHE_KEY);
    if (raw) cache = JSON.parse(raw);
  } catch (e) { cache = null; }

  const now = Date.now();
  if (cache && cache.fetchedAt && (now - cache.fetchedAt) < PATCHNOTES_TTL_MS && Array.isArray(cache.items)) {
    renderPatchnotes(cache.items, listEl);
    return;
  }

  try {
    const res = await fetch(`https://api.github.com/repos/${repo}/pulls?state=closed&sort=updated&direction=desc&per_page=30`, {
      headers: { "Accept": "application/vnd.github+json" }
    });
    if (!res.ok) throw new Error(`GitHub API ${res.status}`);
    const prs = await res.json();
    const merged = (Array.isArray(prs) ? prs : [])
      .filter(pr => pr && pr.merged_at)
      .sort((a, b) => new Date(b.merged_at) - new Date(a.merged_at))
      .slice(0, 3);
    renderPatchnotes(merged, listEl);
    try {
      localStorage.setItem(PATCHNOTES_CACHE_KEY, JSON.stringify({ fetchedAt: now, items: merged }));
    } catch (e) { /* ignore quota */ }
  } catch (e) {
    if (cache && Array.isArray(cache.items)) {
      renderPatchnotes(cache.items, listEl);
    }
  }
}

loadPatchnotes();

applyTheme(state.theme, { persist: false });
renderKpiStaticInstructions();
renderKpiSections();
renderKpiOptions();
renderExpenseRows();
renderOtRows();
renderOtherForms();
renderUpcomingHolidays();

// ----- Reusable in-app confirm modal (replaces window.confirm) -----
function confirmDialog({ title = "Confirm", message = "", confirmLabel = "Confirm", cancelLabel = "Cancel", danger = false } = {}) {
  return new Promise(resolve => {
    const overlay = document.createElement("div");
    overlay.className = "modal-overlay";
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");

    const panel = document.createElement("div");
    panel.className = `modal-panel${danger ? " modal-danger" : ""}`;

    const heading = document.createElement("h2");
    heading.textContent = title;
    panel.appendChild(heading);

    if (message) {
      const body = document.createElement("p");
      body.className = "modal-message";
      body.textContent = message;
      panel.appendChild(body);
    }

    const actions = document.createElement("div");
    actions.className = "modal-actions";
    const cancelBtn = document.createElement("button");
    cancelBtn.type = "button";
    cancelBtn.className = "modal-cancel";
    cancelBtn.textContent = cancelLabel;
    const confirmBtn = document.createElement("button");
    confirmBtn.type = "button";
    confirmBtn.className = danger ? "danger-button" : "modal-confirm";
    confirmBtn.textContent = confirmLabel;
    actions.appendChild(cancelBtn);
    actions.appendChild(confirmBtn);
    panel.appendChild(actions);
    overlay.appendChild(panel);
    document.body.appendChild(overlay);

    let settled = false;
    const close = result => {
      if (settled) return;
      settled = true;
      overlay.remove();
      document.removeEventListener("keydown", onKey);
      resolve(result);
    };
    const onKey = event => {
      if (event.key === "Escape") close(false);
      else if (event.key === "Enter") close(true);
    };
    cancelBtn.addEventListener("click", () => close(false));
    confirmBtn.addEventListener("click", () => close(true));
    overlay.addEventListener("click", event => { if (event.target === overlay) close(false); });
    document.addEventListener("keydown", onKey);
    setTimeout(() => confirmBtn.focus(), 0);
  });
}
