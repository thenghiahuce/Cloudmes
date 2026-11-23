-- CHAY MOT LAN TRONG pgAdmin 4 > Query Tool, database testmes.
-- Sao luu CSDL truoc khi chay. KHONG xoa cong don, lich su AI hay tai khoan hoat dong.
-- Chi xoa VINH VIEN tai khoan customer co is_active=FALSE, KHONG CO cong don
-- va KHONG CO bat ky khoa ngoai nao dang tham chieu.
-- Neu cong ty co don CHUA HOAN THANH, hien 'Tai khoan dang co cong don san xuat'.
-- Neu cong ty co don HOAN THANH, GIU lai theo yeu cau de bao toan lich su.
BEGIN;
SET LOCAL lock_timeout = '8s';
CREATE TEMP TABLE cleanup_customer_result (
  username text, company_name text, result text, detail text
) ON COMMIT PRESERVE ROWS;
DO $cleanup$
DECLARE
  a record;
  fk record;
  has_ref boolean;
  reason text;
  status_name text;
  checked_company bigint;
BEGIN
  PERFORM pg_advisory_xact_lock(2026,1118);
  FOR a IN
    SELECT u.id, u.username, u.customer_company_id, c.company_name
      FROM app_users u
      JOIN customer_companies c ON c.id=u.customer_company_id
      WHERE u.role='customer' AND u.is_active=FALSE
      ORDER BY u.id FOR UPDATE OF u
  LOOP
    -- Chan NEU CONG TY CO BAT KY CONG DON NAO (ke ca da hoan thanh).
    SELECT o.status INTO status_name FROM customer_orders o
      WHERE o.company_id=a.customer_company_id OR o.created_by=a.id
      ORDER BY CASE WHEN o.status='completed' THEN 1 ELSE 0 END LIMIT 1;
    IF FOUND THEN
      reason := CASE WHEN status_name='completed'
        THEN 'Tai khoan co cong don da hoan thanh: giu lich su, KHONG xoa'
        ELSE 'Tai khoan dang co cong don san xuat, KHONG the xoa' END;
      INSERT INTO cleanup_customer_result VALUES (a.username,a.company_name,'GIU LAI',reason);
      CONTINUE;
    END IF;

    reason := NULL;
    -- Tim TAT CA khoa ngoai 1 cot tham chieu app_users(id), ke ca ON DELETE CASCADE.
    FOR fk IN
      SELECT ns.nspname AS schema_name, rel.relname AS table_name,
             att.attname AS column_name
        FROM pg_constraint c
        JOIN pg_class rel ON rel.oid=c.conrelid
        JOIN pg_namespace ns ON ns.oid=rel.relnamespace
        JOIN pg_attribute att ON att.attrelid=c.conrelid AND att.attnum=c.conkey[1]
        JOIN pg_attribute target_att ON target_att.attrelid=c.confrelid
             AND target_att.attnum=c.confkey[1]
        WHERE c.contype='f' AND c.confrelid='public.app_users'::regclass
          AND array_length(c.conkey,1)=1 AND array_length(c.confkey,1)=1
          AND target_att.attname='id'
    LOOP
      EXECUTE format('SELECT EXISTS(SELECT 1 FROM %I.%I WHERE %I=$1)',
        fk.schema_name,fk.table_name,fk.column_name) INTO has_ref USING a.id;
      IF has_ref THEN
        reason := COALESCE(reason||', ','Du lieu lien ket: ')||fk.table_name;
      END IF;
    END LOOP;
    IF reason IS NOT NULL THEN
      INSERT INTO cleanup_customer_result VALUES (a.username,a.company_name,'GIU LAI',reason);
      CONTINUE;
    END IF;
    BEGIN
      DELETE FROM app_users u WHERE u.id=a.id AND u.role='customer' AND NOT u.is_active;
      INSERT INTO cleanup_customer_result VALUES (a.username,a.company_name,'DA XOA VINH VIEN','Khong co cong don va khong co khoa ngoai tham chieu');
    EXCEPTION WHEN foreign_key_violation THEN
      INSERT INTO cleanup_customer_result VALUES (a.username,a.company_name,'GIU LAI','Con rang buoc khoa ngoai');
    END;
  END LOOP;

  -- Xoa cong ty rong HOAN TOAN, khong con tai khoan/don hay tham chieu khac.
  -- Mac dinh GIU bang customer_companies de tranh tac dong khong mong muon.
END;
$cleanup$;
COMMIT;
SELECT * FROM cleanup_customer_result ORDER BY result,company_name,username;
