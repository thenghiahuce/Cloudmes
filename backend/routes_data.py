"""API dữ liệu: nhân viên, xưởng và dashboard sản xuất."""
import os
import re
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from backend.db import fetch_all, get_connection
from backend.scope import fetch_all_scoped, scope_from_request

router = APIRouter()


@router.get("/api/employees/statuses")
async def employee_statuses():
    """Các giá trị trạng thái nhân viên thực tế trong database (cho ô lọc)."""
    rows = fetch_all("SELECT DISTINCT employment_status AS v FROM employees "
                     "WHERE employment_status IS NOT NULL AND employment_status <> '' ORDER BY 1")
    return [r["v"] for r in rows]
 
 
@router.get("/api/employees")
async def list_employees(q: str = "", workshop_id: int | None = None, status: str = ""):
    """Danh sách nhân viên từ PostgreSQL, có lọc theo từ khóa/xưởng/trạng thái."""
    active_values = ("Đang làm", "Đang làm việc", "Active")
    status = status.strip()
    # Chấp nhận cả giá trị cũ Active/Inactive lẫn giá trị tiếng Việt thật trong database.
    if status == "Active":
        status_sql = "AND COALESCE(e.employment_status, '') = ANY(%s)"
        status_param = list(active_values)
    elif status == "Inactive":
        status_sql = "AND COALESCE(e.employment_status, '') <> ALL(%s)"
        status_param = list(active_values)
    elif status:
        status_sql = "AND COALESCE(e.employment_status, '') = %s"
        status_param = status
    else:
        status_sql = "AND (%s = '' OR TRUE)"
        status_param = ""
    sql = f"""
    SELECT e.id, e.employee_code, e.employee_name, e.position, e.gender,
           e.hire_date, e.employment_status, w.workshop_code, w.workshop_name
    FROM employees e
    LEFT JOIN workshops w ON w.id = e.workshop_id
    WHERE (%s = '' OR e.employee_code ILIKE %s OR e.employee_name ILIKE %s
           OR COALESCE(e.position, '') ILIKE %s)
      AND (%s IS NULL OR e.workshop_id = %s)
      {status_sql}
    ORDER BY e.employee_code
    """
    term = f"%{q.strip()}%"
    return fetch_all(sql, (q.strip(), term, term, term, workshop_id, workshop_id, status_param))
 
 
@router.get("/api/workshops")
async def list_workshops():
    return fetch_all("SELECT id, workshop_code, workshop_name FROM workshops ORDER BY workshop_name")
 
 
@router.get("/api/dashboard/summary")
async def dashboard_summary(request: Request):
    """Tổng quan PO - chỉ tính các PO/máy nằm trong phạm vi của người dùng."""
    scope = scope_from_request(request)
    sql = """
    WITH process_rows AS (
        SELECT
            po.id AS po_id,
            po.planned_quantity,
            po.status,
            pp.process_order,
            COALESCE(SUM(pr.quantity_produced), 0) AS quantity_produced
        FROM production_orders po
        LEFT JOIN production_records pr
            ON pr.production_order_id = po.id
        LEFT JOIN machines m
            ON m.id = pr.machine_id
        LEFT JOIN production_processes pp
            ON pp.id = m.process_id
        GROUP BY po.id, po.planned_quantity, po.status, pp.process_order
    ),
    final_output AS (
        SELECT DISTINCT ON (po_id)
            po_id,
            quantity_produced AS actual_quantity
        FROM process_rows
        WHERE process_order IS NOT NULL
        ORDER BY po_id, process_order DESC
    )
    SELECT
        COUNT(*)::int AS total_po,
        COUNT(*) FILTER (WHERE po.status = 'In Progress')::int AS in_progress,
        COUNT(*) FILTER (WHERE po.status = 'Completed')::int AS completed,
        COUNT(*) FILTER (WHERE po.status = 'Planned')::int AS planned,
        COALESCE(SUM(po.planned_quantity), 0)::int AS planned_quantity,
        COALESCE(SUM(fo.actual_quantity), 0)::int AS actual_quantity,
        CASE
            WHEN COALESCE(SUM(po.planned_quantity) FILTER (WHERE po.status <> 'Planned'), 0) = 0 THEN 0
            ELSE LEAST(100, GREATEST(0, ROUND(
                100.0 * COALESCE(SUM(fo.actual_quantity) FILTER (WHERE po.status <> 'Planned'), 0)
                / SUM(po.planned_quantity) FILTER (WHERE po.status <> 'Planned'), 2)))
        END AS completion_percent
    FROM production_orders po
    LEFT JOIN final_output fo ON fo.po_id = po.id;
    """
    rows = fetch_all_scoped(scope, sql)
    return rows[0] if rows else {}
 
 
@router.get("/api/dashboard/pos")
async def dashboard_pos(request: Request):
    """
    Danh sách PO cho Dashboard (chỉ PO/máy trong phạm vi của người dùng).
 
    Dùng LEFT JOIN để PO vẫn xuất hiện ngay cả khi thiếu record sản xuất.
    Sản lượng thực tế lấy ở công đoạn cuối theo process_order, không cộng
    sản lượng của các công đoạn.
    """
    sql = """
    WITH process_rows AS (
        SELECT
            po.id AS po_id,
            po.order_code,
            po.planned_quantity,
            po.status,
            po.actual_start,
            po.actual_end,
            p.product_code,
            p.product_name,
            w.workshop_name,
            pp.process_order,
            COALESCE(SUM(pr.quantity_produced), 0)::int AS quantity_produced
        FROM production_orders po
        LEFT JOIN products p ON p.id = po.product_id
        LEFT JOIN workshops w ON w.id = po.workshop_id
        LEFT JOIN production_records pr ON pr.production_order_id = po.id
        LEFT JOIN machines m ON m.id = pr.machine_id
        LEFT JOIN production_processes pp ON pp.id = m.process_id
        GROUP BY
            po.id, po.order_code, po.planned_quantity, po.status,
            po.actual_start, po.actual_end, p.product_code,
            p.product_name, w.workshop_name, pp.process_order
    ),
    final_output AS (
        SELECT DISTINCT ON (po_id)
            po_id, order_code, planned_quantity, status,
            actual_start, actual_end, product_code, product_name,
            workshop_name, quantity_produced AS actual_quantity
        FROM process_rows
        ORDER BY po_id, process_order DESC NULLS LAST
    ),
    po_quality AS (
        SELECT production_order_id AS po_id,
               COALESCE(SUM(quantity_defective), 0)::int AS process_defects,
               COUNT(*)::int AS record_count
        FROM production_records
        GROUP BY production_order_id
    ),
    po_machines AS (
        -- Các máy thực tế đã chạy PO (theo production_records), xếp theo công đoạn.
        SELECT
            x.po_id,
            json_agg(
                json_build_object(
                    'machine_code', x.machine_code,
                    'machine_name', x.machine_name
                )
                ORDER BY x.process_order NULLS LAST, x.machine_code
            ) AS machines
        FROM (
            SELECT DISTINCT
                pr.production_order_id AS po_id,
                m.machine_code,
                m.machine_name,
                pp.process_order
            FROM production_records pr
            JOIN machines m ON m.id = pr.machine_id
            LEFT JOIN production_processes pp ON pp.id = m.process_id
        ) x
        GROUP BY x.po_id
    )
    SELECT
        order_code, product_code, product_name, workshop_name,
        planned_quantity, actual_quantity,
        CASE
            WHEN lower(status) = 'completed' THEN 100
            WHEN planned_quantity = 0 THEN 0
            ELSE LEAST(100, GREATEST(0, ROUND(
                (100.0 * actual_quantity / planned_quantity)::numeric, 2
            )))
        END AS completion_percent,
        status, actual_start, actual_end,
        COALESCE(pm.machines, '[]'::json) AS machines,
        COALESCE(pq.process_defects, 0) AS process_defects,
        COALESCE(pq.record_count, 0) AS record_count
    FROM final_output fo
    LEFT JOIN po_machines pm ON pm.po_id = fo.po_id
    LEFT JOIN po_quality pq ON pq.po_id = fo.po_id
    ORDER BY
        CASE status
            WHEN 'In Progress' THEN 1
            WHEN 'Planned' THEN 2
            ELSE 3
        END,
        order_code;
    """
    scope = scope_from_request(request)
    try:
        return fetch_all_scoped(scope, sql)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Lỗi /api/dashboard/pos: {type(e).__name__}: {e}"
        )
 
 
@router.get("/api/dashboard/po/{order_code}")
async def dashboard_po(order_code: str, request: Request):
    scope = scope_from_request(request)
    header_sql = """
    SELECT
        po.order_code,
        p.product_code,
        p.product_name,
        w.workshop_name,
        po.planned_quantity,
        po.planned_start,
        po.planned_end,
        po.actual_start,
        po.actual_end,
        po.status
    FROM production_orders po
    JOIN products p ON p.id = po.product_id
    JOIN workshops w ON w.id = po.workshop_id
    WHERE po.order_code = %s;
    """
    header = fetch_all_scoped(scope, header_sql, (order_code,))
    if not header:
        # PO không tồn tại HOẶC không thuộc máy nào mình quản lý: trả cùng một lỗi.
        raise HTTPException(status_code=404, detail="Không tìm thấy PO")
 
    line_sql = """
    SELECT
        pp.process_order,
        pp.process_code,
        pp.process_name,
        m.machine_code,
        m.machine_name,
        COALESCE(SUM(pr.quantity_produced), 0)::int AS quantity_produced,
        COALESCE(SUM(pr.quantity_defective), 0)::int AS quantity_defective,
        COALESCE(SUM(pr.production_minutes), 0)::int AS production_minutes,
        CASE WHEN COALESCE(SUM(pr.quantity_produced), 0) = 0 THEN 0
             ELSE ROUND(100.0 * SUM(pr.quantity_defective) / SUM(pr.quantity_produced), 2)
        END AS defect_rate
    FROM production_orders po
    JOIN production_records pr ON pr.production_order_id = po.id
    JOIN machines m ON m.id = pr.machine_id
    JOIN production_processes pp ON pp.id = m.process_id
    WHERE po.order_code = %s
    GROUP BY pp.process_order, pp.process_code, pp.process_name,
             m.machine_code, m.machine_name
    ORDER BY pp.process_order;
    """
    line = fetch_all_scoped(scope, line_sql, (order_code,))
 
    quality_sql = """
    SELECT
        qi.defect_type,
        SUM(qi.failed_quantity)::int AS failed_quantity,
        SUM(qi.total_checked)::int AS total_checked,
        CASE WHEN SUM(qi.total_checked) = 0 THEN 0
             ELSE ROUND(100.0 * SUM(qi.failed_quantity) / SUM(qi.total_checked), 2)
        END AS defect_rate
    FROM quality_inspections qi
    JOIN production_records pr ON pr.id = qi.production_record_id
    JOIN production_orders po ON po.id = pr.production_order_id
    WHERE po.order_code = %s
      AND qi.defect_type IS NOT NULL
    GROUP BY qi.defect_type
    ORDER BY failed_quantity DESC;
    """
    quality = fetch_all_scoped(scope, quality_sql, (order_code,))
 
    # ------------------------------------------------------------
    # STEP 6 - DOWNTIME LIÊN QUAN CÁC MÁY CỦA PO
    # ------------------------------------------------------------
    # machine_logs trong database hiện tại CÓ production_order_id.
    # Downtime của PO phải được lọc trực tiếp theo khóa PO này.
    downtime_sql = """
    SELECT
        m.machine_code,
        m.machine_name,
        pp.process_code,
        pp.process_name,
        COALESCE(ml.downtime_minutes, 0)::int AS downtime_minutes,
        ml.reason,
        ml.start_time,
        ml.end_time
    FROM machine_logs ml
    JOIN production_orders po ON po.id = ml.production_order_id
    JOIN machines m ON m.id = ml.machine_id
    LEFT JOIN production_processes pp ON pp.id = m.process_id
    WHERE po.order_code = %s
      AND COALESCE(ml.downtime_minutes, 0) > 0
    ORDER BY ml.downtime_minutes DESC, ml.start_time;
    """
    downtime = fetch_all_scoped(scope, downtime_sql, (order_code,))
 
    total_downtime_minutes = sum(
        int(r.get("downtime_minutes") or 0) for r in downtime
    )
 
    # ------------------------------------------------------------
    # STRUCTURED PO ANALYSIS
    # ------------------------------------------------------------
    # The analysis below is deterministic and based only on PostgreSQL data.
    # This gives the UI a stable analysis payload while Vanna AI remains
    # responsible for natural-language questions.
    planned = int(header[0].get("planned_quantity") or 0)
    first_qty = int(line[0].get("quantity_produced") or 0) if line else 0
    final_qty = int(line[-1].get("quantity_produced") or 0) if line else 0
 
    completion_percent = (100.0 if str(header[0].get("status") or "").lower() == "completed" else min(100.0, round(100.0 * final_qty / planned, 2))) if planned else 0.0
    total_loss = max(first_qty - final_qty, 0)
    loss_percent = round(100.0 * total_loss / first_qty, 2) if first_qty else 0.0
 
    # Find the process with the highest defect rate. Tie-break by defect count.
    attention_process = None
    if line:
        attention_process = max(
            line,
            key=lambda r: (
                float(r.get("defect_rate") or 0),
                int(r.get("quantity_defective") or 0),
            ),
        )
 
    total_production_minutes = sum(
        int(r.get("production_minutes") or 0) for r in line
    )
 
    quality_total_failed = sum(
        int(r.get("failed_quantity") or 0) for r in quality
    )
 
    recommendations = []
 
    if attention_process:
        code = attention_process.get("process_code")
        name = attention_process.get("process_name") or code
        defect_rate = float(attention_process.get("defect_rate") or 0)
        defective = int(attention_process.get("quantity_defective") or 0)
 
        if defect_rate > 0 or defective > 0:
            recommendations.append(
                f"Ưu tiên kiểm tra công đoạn {name} ({code}): "
                f"{defective} sản phẩm lỗi, tỷ lệ lỗi {defect_rate:.2f}%."
            )
 
    if total_loss > 0:
        recommendations.append(
            f"Rà soát điểm phát sinh hao hụt giữa đầu và cuối dây chuyền: "
            f"{total_loss} sản phẩm ({loss_percent:.2f}%)."
        )
 
    if quality_total_failed > 0:
        recommendations.append(
            f"Phân tích nguyên nhân các lỗi chất lượng đã ghi nhận: "
            f"{quality_total_failed} lỗi."
        )
 
    if total_downtime_minutes > 0:
        recommendations.append(
            f"Ưu tiên xử lý downtime của PO: tổng {total_downtime_minutes} phút, "
            f"trong đó máy có downtime lớn nhất cần được kiểm tra trước."
        )
 
    if not recommendations:
        recommendations.append(
            "Chưa phát hiện tín hiệu bất thường rõ ràng từ dữ liệu PO hiện có."
        )
 
    analysis = {
        "planned_quantity": planned,
        "first_process_quantity": first_qty,
        "final_process_quantity": final_qty,
        "completion_percent": completion_percent,
        "total_loss": total_loss,
        "loss_percent": loss_percent,
        "total_production_minutes": total_production_minutes,
        "total_downtime_minutes": total_downtime_minutes,
        "quality_failed_quantity": quality_total_failed,
        "attention_process": attention_process,
        "recommendations": recommendations,
        "data_limitations": [
            "Downtime được liên kết trực tiếp với PO qua machine_logs.production_order_id.",
            "Các kết luận chỉ dựa trên dữ liệu hiện có trong PostgreSQL."
        ],
    }
 
    return {
        "order": header[0],
        "line": line,
        "quality": quality,
        "downtime": downtime,
        "analysis": analysis,
        "downtime_note": (
            f"Downtime của PO {order_code} được liên kết trực tiếp từ "
            f"machine_logs.production_order_id. Tổng downtime: "
            f"{total_downtime_minutes} phút."
        ),
    }
