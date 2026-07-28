CREATE DATABASE IF NOT EXISTS officeform;
USE officeform;

CREATE TABLE IF NOT EXISTS users (
    id            INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    worker_id     VARCHAR(20) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NULL,
    role          ENUM('worker','admin') NOT NULL DEFAULT 'worker',
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS workers (
    worker_id                VARCHAR(20) PRIMARY KEY,
    name                     VARCHAR(255) NOT NULL,
    designation              VARCHAR(255),
    department               VARCHAR(255),
    house_tel                VARCHAR(50),
    other_tel                VARCHAR(50),
    evaluator_name           VARCHAR(255),
    annual_leave_entitlement DECIMAL(5,1) DEFAULT 0,
    annual_leave_taken       DECIMAL(5,1) DEFAULT 0,
    employment_type          ENUM('permanent','contract') DEFAULT 'permanent',
    employment_start_date    DATE,
employment_end_date    DATE,
    calendar_name        VARCHAR(60) NULL,
    profile_complete     BOOLEAN DEFAULT FALSE,
    updated_at               DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS submissions (
    id                  VARCHAR(30) PRIMARY KEY,
    worker_id           VARCHAR(20) NOT NULL,
    form_type           VARCHAR(10) NOT NULL,
    form_name           VARCHAR(100),
    leave_type          VARCHAR(20),
    start_date          DATE,
    end_date            DATE,
    duration_days       DECIMAL(4,1),
    affects_al          BOOLEAN DEFAULT FALSE,
    al_days_applied     DECIMAL(4,1) DEFAULT 0,
    is_half_day         BOOLEAN DEFAULT FALSE,
    half_day_period     VARCHAR(2),
    reason              TEXT,
    kpi_month           VARCHAR(7),
    application_date    DATE,
    kpi_data            JSON,
    worker_snapshot     JSON,
    leave_summary       JSON,
    pdf_file_name       VARCHAR(255),
    workbook_file_name  VARCHAR(255),
    sheets_synced_at    DATETIME NULL,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (worker_id) REFERENCES workers(worker_id)
);
