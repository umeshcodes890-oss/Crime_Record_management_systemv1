-- =====================================================================
-- Migration 000 - infrastructure for every migration that follows
--
-- MySQL 8.0 has no "ADD COLUMN IF NOT EXISTS" (that is MariaDB), so the
-- migration files would not be re-runnable without help. These two
-- helpers check information_schema first and only then run the DDL,
-- which is the same idiom schema.sql already uses for
-- fk_station_incharge.
--
-- schema_migrations is the ledger: scripts/migrate.py records every
-- file it has applied, together with a checksum, so a file that is
-- edited after being applied is reported as drift.
-- =====================================================================

CREATE TABLE IF NOT EXISTS schema_migrations (
    filename    VARCHAR(200) NOT NULL,
    checksum    CHAR(64)     NOT NULL,
    applied_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (filename)
) ENGINE = InnoDB;

DELIMITER $$

DROP PROCEDURE IF EXISTS sp_add_column $$
CREATE PROCEDURE sp_add_column(
    IN p_table      VARCHAR(64),
    IN p_column     VARCHAR(64),
    IN p_definition VARCHAR(2000)
)
BEGIN
    DECLARE v_exists INT DEFAULT 0;

    SELECT COUNT(*) INTO v_exists
      FROM information_schema.COLUMNS
     WHERE TABLE_SCHEMA  = DATABASE()
       AND TABLE_NAME    = p_table
       AND COLUMN_NAME   = p_column;

    IF v_exists = 0 THEN
        SET @ddl := CONCAT('ALTER TABLE `', p_table, '` ADD COLUMN `',
                           p_column, '` ', p_definition);
        PREPARE stmt FROM @ddl;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END $$

DROP PROCEDURE IF EXISTS sp_modify_column $$
CREATE PROCEDURE sp_modify_column(
    IN p_table      VARCHAR(64),
    IN p_column     VARCHAR(64),
    IN p_definition VARCHAR(2000)
)
BEGIN
    DECLARE v_exists INT DEFAULT 0;

    SELECT COUNT(*) INTO v_exists
      FROM information_schema.COLUMNS
     WHERE TABLE_SCHEMA = DATABASE()
       AND TABLE_NAME   = p_table
       AND COLUMN_NAME  = p_column;

    -- Re-running a MODIFY with the same definition is harmless, so this
    -- only has to guard against the column not existing yet.
    IF v_exists = 1 THEN
        SET @ddl := CONCAT('ALTER TABLE `', p_table, '` MODIFY COLUMN `',
                           p_column, '` ', p_definition);
        PREPARE stmt FROM @ddl;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END $$

DROP PROCEDURE IF EXISTS sp_add_index $$
CREATE PROCEDURE sp_add_index(
    IN p_table      VARCHAR(64),
    IN p_index      VARCHAR(64),
    IN p_definition VARCHAR(2000)
)
BEGIN
    DECLARE v_exists INT DEFAULT 0;

    SELECT COUNT(*) INTO v_exists
      FROM information_schema.STATISTICS
     WHERE TABLE_SCHEMA = DATABASE()
       AND TABLE_NAME   = p_table
       AND INDEX_NAME   = p_index;

    IF v_exists = 0 THEN
        SET @ddl := CONCAT('ALTER TABLE `', p_table, '` ADD ', p_definition);
        PREPARE stmt FROM @ddl;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END $$

DELIMITER ;
