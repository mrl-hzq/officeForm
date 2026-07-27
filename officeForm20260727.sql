CREATE DATABASE  IF NOT EXISTS `officeform` /*!40100 DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci */ /*!80016 DEFAULT ENCRYPTION='N' */;
USE `officeform`;
-- MySQL dump 10.13  Distrib 8.0.42, for Win64 (x86_64)
--
-- Host: 127.0.0.1    Database: officeform
-- ------------------------------------------------------
-- Server version	8.0.41

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `submissions`
--

DROP TABLE IF EXISTS `submissions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `submissions` (
  `id` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `worker_id` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `form_type` varchar(10) COLLATE utf8mb4_unicode_ci NOT NULL,
  `form_name` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `leave_type` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `start_date` date DEFAULT NULL,
  `end_date` date DEFAULT NULL,
  `duration_days` int DEFAULT NULL,
  `affects_al` tinyint(1) DEFAULT '0',
  `al_days_applied` int DEFAULT '0',
  `reason` text COLLATE utf8mb4_unicode_ci,
  `kpi_month` varchar(7) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `application_date` date DEFAULT NULL,
  `kpi_data` json DEFAULT NULL,
  `worker_snapshot` json DEFAULT NULL,
  `leave_summary` json DEFAULT NULL,
  `pdf_file_name` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `workbook_file_name` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `worker_id` (`worker_id`),
  CONSTRAINT `submissions_ibfk_1` FOREIGN KEY (`worker_id`) REFERENCES `workers` (`worker_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `submissions`
--

LOCK TABLES `submissions` WRITE;
/*!40000 ALTER TABLE `submissions` DISABLE KEYS */;
INSERT INTO `submissions` VALUES ('EXP-8F16A106','C0036','EXP','Expense Claim',NULL,'2026-06-22','2026-06-23',2,0,0,'2026-06 expense claim','2026-06','2026-06-24','{\"site\": \"FCS\", \"items\": [{\"date\": \"2026-06-22\", \"misc\": 0, \"toll\": 22.44, \"hotel\": 0, \"phone\": 0, \"total\": 362.13, \"flight\": 0, \"medical\": 0, \"mileage\": 249.69, \"parking\": 0, \"project\": \"FCS\", \"totalKm\": 287, \"description\": \"Travel to TLDM Lumut  by Car\", \"entertainment\": 0, \"transportMode\": \"car\", \"travelAllowance\": 90}, {\"date\": \"2026-06-23\", \"misc\": 0, \"toll\": 17.29, \"hotel\": 0, \"phone\": 0, \"total\": 356.98, \"flight\": 0, \"medical\": 0, \"mileage\": 249.69, \"parking\": 0, \"project\": \"FCS\", \"totalKm\": 287, \"description\": \"Travel to Mindmatic by Car\", \"entertainment\": 0, \"transportMode\": \"car\", \"travelAllowance\": 90}], \"advances\": 0.0, \"claimMonth\": \"2026-06\", \"totalAmount\": 719.11, \"supervisorName\": \"Mohamad Azmadi bin Angit @ Asra Ramlan\", \"amountToReimburse\": 719.11}','{\"name\": \"MUHAMMAD AMIRUL HAZIQ BIN KASAMANI\", \"workerId\": \"C0036\", \"department\": \"COMMAND CENTRE\", \"designation\": \"APPLICATION DEVELOPER\", \"evaluatorName\": \"Mohamad Azmadi bin Angit @ Asra Ramlan\"}',NULL,'C0036_EXP_2026-06_EXP-8F16A106.pdf','C0036_EXP_2026-06_EXP-8F16A106.xlsx','2026-06-24 05:01:54'),('OT-92F7341D','C0036','OT','Overtime Claim',NULL,'2026-06-28','2026-06-28',1,0,0,'2026-06 overtime claim','2026-06','2026-07-15','{\"items\": [{\"date\": \"2026-06-28\", \"hours\": 5, \"timeTo\": \"1900\", \"dayLabel\": \"Sunday\", \"rateType\": \"rest\", \"timeFrom\": \"1400\", \"description\": \"Develop AI workflow for presentation in Jakarta\"}], \"claimMonth\": \"2026-06\", \"totalHours\": 5.0, \"hoursByRate\": {\"rest\": 5.0, \"normal\": 0, \"holiday\": 0}}','{\"name\": \"MUHAMMAD AMIRUL HAZIQ BIN KASAMANI\", \"workerId\": \"C0036\", \"department\": \"COMMAND CENTRE\", \"designation\": \"APPLICATION DEVELOPER\"}',NULL,'C0036_OT_2026-06_OT-92F7341D.pdf','C0036_OT_2026-06_OT-92F7341D.xls','2026-07-15 02:36:14');
/*!40000 ALTER TABLE `submissions` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `users`
--

DROP TABLE IF EXISTS `users`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `users` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `worker_id` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `password_hash` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `role` enum('worker','admin') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'worker',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `worker_id` (`worker_id`)
) ENGINE=InnoDB AUTO_INCREMENT=11 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `users`
--

LOCK TABLES `users` WRITE;
/*!40000 ALTER TABLE `users` DISABLE KEYS */;
INSERT INTO `users` VALUES (1,'C0036',NULL,'admin','2026-06-04 15:24:27');
/*!40000 ALTER TABLE `users` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `workers`
--

DROP TABLE IF EXISTS `workers`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `workers` (
  `worker_id` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `designation` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `department` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `house_tel` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `other_tel` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `evaluator_name` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `annual_leave_entitlement` decimal(5,1) DEFAULT '0.0',
  `annual_leave_taken` decimal(5,1) DEFAULT '0.0',
  `employment_type` enum('permanent','contract') COLLATE utf8mb4_unicode_ci DEFAULT 'permanent',
  `employment_start_date` date DEFAULT NULL,
  `employment_end_date` date DEFAULT NULL,
  `profile_complete` tinyint(1) DEFAULT '0',
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`worker_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `workers`
--

LOCK TABLES `workers` WRITE;
/*!40000 ALTER TABLE `workers` DISABLE KEYS */;
INSERT INTO `workers` VALUES ('C0036','Muhammad Amirul Haziq bin Kasamani','Application Developer','Command Centre','-','01116301216','Mohamad Azmadi bin Angit @ Asra Ramlan',14.0,0.0,'contract','2025-07-01','2026-07-31',1,'2026-07-15 10:36:46');
/*!40000 ALTER TABLE `workers` ENABLE KEYS */;
UNLOCK TABLES;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-07-27 12:14:05
