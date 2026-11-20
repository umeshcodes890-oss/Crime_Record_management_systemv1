-- =====================================================================
-- Migration 004 - Audit logging
--
-- One table recording who changed what and when. The repositories write
-- to it (phase B) because they are the only layer that knows both the
-- signed-in user and the reason for a change; a trigger could record the
-- id but not the intent.
--
-- changed_by_user_id is nullable and SET NULL on delete, paired with
-- username_snapshot, so removing a user account cannot destroy the
-- history of what that person did. An audit trail that vanishes when a
-- login is deleted is not an audit trail.
--
-- The log has no update or delete path: corrections are appended as new
-- entries, the same rule the evidence custody log follows.
-- =====================================================================

CREATE TABLE IF NOT EXISTS audit_log (
    audit_id            BIGINT       NOT NULL AUTO_INCREMENT,
    entity              VARCHAR(40)  NOT NULL,
    entity_id           INT          NOT NULL,
    case_id             INT          NULL,
    action              ENUM('create','update','delete','status_change',
                             'login','permission_change','file_attach')
                        NOT NULL,
    summary             VARCHAR(500) NULL,
    changed_by_user_id  INT          NULL,
    username_snapshot   VARCHAR(80)  NULL,
    changed_at          TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (audit_id),
    KEY idx_audit_entity (entity, entity_id),
    KEY idx_audit_case (case_id),
    KEY idx_audit_user (changed_by_user_id),
    KEY idx_audit_time (changed_at),
    CONSTRAINT fk_audit_case FOREIGN KEY (case_id)
        REFERENCES crime_cases (case_id)
        ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT fk_audit_user FOREIGN KEY (changed_by_user_id)
        REFERENCES users (user_id)
        ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE = InnoDB;

-- ---------------------------------------------------------------------
-- Append-only, enforced in the database so no application bug or direct
-- SQL session can quietly rewrite history.
--
-- audit_log has no cascading foreign keys pointing INTO it from a parent
-- being deleted, so unlike evidence_custody_log there is no legitimate
-- cascade for these guards to obstruct.
-- ---------------------------------------------------------------------
DELIMITER $$

DROP TRIGGER IF EXISTS trg_audit_log_before_update $$
CREATE TRIGGER trg_audit_log_before_update
BEFORE UPDATE ON audit_log
FOR EACH ROW
BEGIN
    SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Audit log entries are append-only and cannot be edited';
END $$

DROP TRIGGER IF EXISTS trg_audit_log_before_delete $$
CREATE TRIGGER trg_audit_log_before_delete
BEFORE DELETE ON audit_log
FOR EACH ROW
BEGIN
    SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Audit log entries are append-only and cannot be deleted';
END $$

DELIMITER ;
