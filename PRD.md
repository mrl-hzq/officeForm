# Product Requirements Document: Office Form PDF System

## 1. Overview

This project is a simple web-based internal office form system. A worker logs in using their worker ID, chooses an available office form, fills in the required fields, and generates a PDF output based on the existing office form template.

The first version focuses only on form submission and PDF generation. It is not an approval system, HR system, payroll system, or reporting dashboard.

## 2. Goals

- Allow workers to access the system using only their worker ID.
- Load saved worker information from the worker ID to reduce repeated typing.
- Allow workers to choose from supported office forms.
- Allow workers to fill in form details through a web interface.
- Generate a PDF that follows the original office template layout.
- Save completed submissions so generated PDFs can be viewed or downloaded again later.
- Provide a calendar view for date-based submissions such as AL, EL, MC, and other future dated forms.
- Add forms one by one after each template is reviewed.

## 3. Users

### Worker

The worker is the main user of the system.

Workers can:

- Log in using worker ID.
- Select an available form.
- Fill in the form.
- Generate a PDF.
- View and download their previous generated PDFs.
- View their own date-based submissions in a calendar.

### Admin or Office Staff

Admin or office staff can manage form records and templates.

Admin or office staff can:

- View submitted form records.
- Search submissions by worker ID, form type, or date.
- Download generated PDFs.
- Add or update form templates when needed.
- View all workers' date-based submissions in a calendar.

## 4. Supported Forms

The system should support these form categories:

- AL form
- EL form
- MC form
- KPI form

The forms will be reviewed and implemented one by one. The first form to review and implement is the leave form template:

- `Leave Application Form.xls`

Existing templates found in the project folder:

- `Leave Application Form.xls`
- `MC FORM .xls`
- `Borang Penilaian Prestasi (Non Leader).xlsx`
- `expenses claim form baru.xlsx`
- `OT Form latest.xls`

Expenses claim and OT are not part of the first requested scope unless added later.

## 5. Core Workflow

1. Worker opens the web system.
2. Worker enters their worker ID.
3. System validates or accepts the worker ID.
4. System loads saved worker information linked to that worker ID.
5. Worker sees a list of available forms.
6. Worker selects a form.
7. System displays the web form fields for that template and pre-fills matching worker information.
8. Worker fills in or updates the required information.
9. Worker previews or confirms the form.
10. System generates a PDF using the matching office template.
11. System saves the completed submission record.
12. Worker can download the generated PDF.
13. Worker can view dated submissions in the calendar view.

## 6. Authentication Requirements

### Worker ID Login

The first version uses worker ID only.

Requirements:

- Login screen must contain a worker ID input.
- Worker ID is required.
- Worker ID should be stored with every submission.
- Worker ID should be used to load saved worker information for form pre-fill.
- The system should support future validation against a staff list.

Not required for the first version:

- Password login
- PIN login
- Email login
- Two-factor authentication
- Single sign-on

## 7. Form Selection Requirements

After login, the worker should see a form selection page.

Each form option should show:

- Form name
- Form type
- Availability status

Only completed templates should be selectable. Forms that are not yet reviewed can be hidden or shown as unavailable.

Initial selectable form:

- Leave form, after the `Leave Application Form.xls` template has been mapped.

## 8. Form Entry Requirements

Each form should have a web input screen based on its template.

For every template, the system must define:

- Field name
- Field type
- Required or optional status
- Validation rule, if any
- Template location where the value should appear
- PDF output behavior

Common field types may include:

- Text input
- Date input
- Number input
- Dropdown
- Checkbox
- File upload, if needed by the template

The exact fields must be confirmed during template review.

## 9. Worker Information Auto-Fill Requirements

The system should store reusable worker information and load it after worker ID login. This makes future form filling faster.

Worker information may include:

- Worker name
- Worker ID
- Department
- Position
- Company or branch
- Contact number
- Supervisor or manager name

The exact worker information fields must be based on the form templates. If a template does not require a worker information field, that field should not be forced into the form.

Auto-fill behavior:

- After login, the system loads the worker profile linked to the worker ID.
- When a worker selects a form, the system checks that form template mapping.
- Only matching fields required by the selected form should be pre-filled.
- Workers can edit pre-filled values before generating the PDF.
- Updated worker information can be saved for future use when appropriate.
- Form-specific values, such as leave dates, MC dates, reasons, KPI scores, or remarks, should not be treated as permanent worker profile data.

## 10. PDF Generation Requirements

The generated PDF must use the existing office template as the source layout.

Requirements:

- PDF output should visually match the original template as closely as possible.
- Worker-entered values must appear in the correct template fields.
- Generated PDFs should be downloadable by the worker.
- Generated PDFs should be saved with the submission record.
- PDF file names should be readable and include worker ID, form type, and submission date.

Recommended PDF file name format:

```text
{worker_id}_{form_type}_{yyyy-mm-dd}_{submission_id}.pdf
```

Example:

```text
EMP001_AL_2026-06-03_0001.pdf
```

## 11. Submission Records

The system should save completed submissions.

Each saved submission should include:

- Submission ID
- Worker ID
- Worker information used in the generated PDF
- Form type
- Submission date and time
- Calendar date or date range, if the form has date fields
- Entered form data
- Generated PDF file reference

Workers should only see their own submissions.

Admin or office staff should be able to see all submissions.

## 12. Calendar View Requirements

The system should include a simple calendar view for date-based form records.

Calendar requirements:

- Show AL, EL, MC, and other future dated form submissions on their related dates.
- Support a monthly calendar view for the first version.
- Use form type labels so workers can quickly see whether an entry is AL, EL, MC, or another form.
- Show date ranges for forms that cover multiple days.
- Allow workers to view only their own calendar entries.
- Allow admin or office staff to view all workers' calendar entries.
- Allow filtering by form type and worker ID for admin or office staff.
- Allow clicking a calendar entry to open the saved submission record or generated PDF.

Calendar data must come from the mapped date fields in each form template. For example, leave forms may use leave start and end dates, while MC forms may use MC start and end dates.

Forms without useful date fields do not need to appear on the calendar unless a relevant date is defined during template review.

## 13. Template Review Process

Each template must be reviewed before it becomes available in the system.

Review steps:

1. Open the original template file.
2. Identify all fillable fields.
3. Identify which fields can be pre-filled from worker information.
4. Identify which date fields should appear in the calendar.
5. Decide which fields are required.
6. Decide each field input type for the web form.
7. Map each web input field to the template location.
8. Generate a test PDF.
9. Compare the PDF output against the original template.
10. Mark the form as ready only after the output is correct.

### First Template: Leave Form

Template file:

```text
Leave Application Form.xls
```

This template should be reviewed first and used to define the first working form in the system.

Expected leave form categories:

- AL
- EL

### Leave Template Field Mapping

The `Leave Application Form.xls` template contains these main fields:

Worker profile fields:

- `NAMA / NAME`
- `NO ID PEKERJA / STAFF ID NO`
- `JAWATAN / DESIGNATION`
- `TEL. RUMAH / HOUSE TEL`
- `LAIN-LAIN TEL. / OTHER TEL. NO`

Leave request fields:

- `JANGKAMASA / DURATION`
- `TARIKH CUTI / DATES OF LEAVE`
- `DARI / FROM`
- `HINGGA / UNTIL`
- Leave type: `CUTI TAHUNAN / ANNUAL LEAVE`
- Leave type: `CUTI TANPA GAJI / UNPAID LEAVE`
- Leave type: `CUTI KECEMASAN / EMERGENCY LEAVE`
- Leave type: `LAIN-LAIN / OTHERS`
- `SEBAB / REASON`

Leave balance fields:

- `KELAYAKAN CUTI / LEAVE ENTITLEMENT`
- `CUTI YANG DIPOHON / LEAVE APPLIED`
- `JUMLAH CUTI YANG TELAH DIAMBIL / LEAVE TAKEN DURING THE YEAR TO DATE`
- `BAKI CUTI / BALANCE OF LEAVE`

Application date fields:

- `HARI / DAY`
- `BULAN / MONTH`
- `TAHUN / YEAR`

Office use fields:

- `DISOKONG / RECOMMENDED`
- `TIDAK DISOKONG / NOT RECOMMENDED`
- `LULUS / APPROVED`
- `TIDAK LULUS / NOT APPROVED`
- `KETUA PEJABAT / HEAD OF DEPT.`
- `URUSAN PENTADBIRAN / ADMINISTRATIVE USE`
- `DIREKOD OLEH / RECORDED BY`
- `HR MANAGER`

Initial observed template locations:

| Template item | Observed location |
| --- | --- |
| Worker name | `L15:AN15` |
| Worker ID | `L17:AN17` |
| Designation | `L19:AN19` |
| House telephone | `L21:S21` |
| Other telephone | `AF21:AN21` |
| Leave duration | `L23:Q23` |
| Leave start date | `R24:Z25` |
| Leave end date | `AG24:AN25` |
| AL reason | `Z28:AN28` |
| Unpaid leave reason | `Z30:AN30` |
| EL reason | `Z32:AN32` |
| Other leave reason | `Z34:AN34` |
| Application day | `A54:C54` |
| Application month | `E54:G54` |
| Application year | `I54:K54` |

Some leave summary and office-use boxes are drawn as Excel rectangle shapes, not plain cells. The implementation must confirm these during PDF mapping and write them in a way that appears correctly in the final PDF.

### AL Form Automation Requirement

For AL, the worker should not need to repeatedly fill in profile or leave balance information.

After the worker logs in using worker ID and selects AL:

- System auto-fills worker name.
- System auto-fills worker ID.
- System auto-fills designation.
- System auto-fills available phone or contact numbers.
- System auto-fills annual leave entitlement, leave taken, and leave balance if available.
- System auto-fills the application date using the current date.
- System marks or maps the leave type as `CUTI TAHUNAN / ANNUAL LEAVE`.
- Worker only needs to select the AL date or AL date range.
- System calculates leave duration from the selected date or date range.
- System generates the PDF using the leave template.

For single-day AL, the start date and end date should be the same.

For multi-day AL, the worker should select a date range. The system should calculate the number of applied leave days from that range.

The AL reason should be automatically filled with a configured default, such as `Annual Leave` or `Personal reason`, unless the office later decides that workers must enter a custom reason.

If required worker profile or leave balance data is missing, the system should clearly show which data is missing before PDF generation.

### Future Template: MC Form

Template file:

```text
MC FORM .xls
```

This form should be reviewed after the leave form.

### Future Template: KPI Form

Template file:

```text
Borang Penilaian Prestasi (Non Leader).xlsx
```

This form should be reviewed after AL, EL, and MC requirements are clear.

## 14. Out of Scope for First Version

The first version does not include:

- Approval workflow
- Email notifications
- WhatsApp notifications
- Payroll integration
- HR system integration
- Leave balance calculation
- KPI scoring automation
- Advanced dashboards
- Password or PIN authentication
- Digital signatures, unless already required by the template

## 15. Acceptance Criteria

The first version is complete when:

- Worker can log in using worker ID only.
- System loads saved worker information from the worker ID.
- Worker can select the first available form.
- Selected form pre-fills matching worker information based on that form template.
- For AL, worker only needs to select the leave date or leave date range when all saved worker and leave balance data is available.
- For AL, duration is calculated automatically from the selected date or date range.
- Worker can fill in the form fields.
- Worker can generate a PDF from the selected template.
- Generated PDF uses the existing template layout.
- Generated PDF contains the worker's submitted values.
- Submission record is saved.
- Worker can download the generated PDF again later.
- Worker can see their own AL, EL, MC, and other dated submissions on a calendar.
- Admin or office staff can see all workers' dated submissions on a calendar.
- Admin or office staff can view saved submissions.

## 16. Implementation Notes

- The first implemented template should be `Leave Application Form.xls`.
- The system should be designed so additional templates can be added without rebuilding the whole application.
- Template mapping should be stored in a maintainable way so field positions can be adjusted after testing.
- Worker profile fields should be mapped separately from form-specific submission fields.
- AL should use saved worker profile and leave balance data so repeated worker fields do not need to be typed every time.
- Calendar fields should be mapped per template, because each form may use different date labels.
- The database should keep form data separately from generated PDF files.
- The generated PDF should be treated as the final output document for office use.
