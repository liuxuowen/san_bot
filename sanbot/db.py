import pymysql
from typing import Any, Iterable, Mapping


def get_connection(cfg: Mapping[str, Any]):
    return pymysql.connect(
        host=cfg.get("MYSQL_HOST", "localhost"),
        port=int(cfg.get("MYSQL_PORT", 3306)),
        user=cfg.get("MYSQL_USER", ""),
        password=cfg.get("MYSQL_PASSWORD", ""),
        database=cfg.get("MYSQL_DB", "sanzhan"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def init_schema(cfg: Mapping[str, Any]) -> None:
    """Create required tables if they do not exist."""
    ddl_users = """
    CREATE TABLE IF NOT EXISTS users (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        openid VARCHAR(64) NOT NULL UNIQUE,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """
    ddl_uploads = """
    CREATE TABLE IF NOT EXISTS uploads (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        user_openid VARCHAR(64) NOT NULL,
        ts DATETIME NOT NULL,
        member_count INT NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_user_ts (user_openid, ts)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """

    ddl_upload_members = """
    CREATE TABLE IF NOT EXISTS upload_members (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        upload_id BIGINT NOT NULL,
        member_name VARCHAR(255) NOT NULL,
        contrib_rank INT NULL,
        contrib_total BIGINT NOT NULL,
        battle_total BIGINT NOT NULL,
        assist_total BIGINT NOT NULL,
        donate_total BIGINT NOT NULL,
        power_value BIGINT NOT NULL,
        group_name VARCHAR(255) NOT NULL,
        CONSTRAINT fk_upload_members_upload
            FOREIGN KEY (upload_id) REFERENCES uploads(id)
            ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """

    conn = get_connection(cfg)
    try:
        with conn.cursor() as cur:
            cur.execute(ddl_users)
            cur.execute(ddl_uploads)
            cur.execute(ddl_upload_members)
        conn.commit()
    finally:
        conn.close()


def insert_upload_with_members(
    cfg: Mapping[str, Any],
    user_openid: str,
    ts,
    members: Iterable[dict[str, Any]],
) -> int:
    """Insert one upload record and its member rows.

    `members` entries should contain keys:
    member_name, rank, contrib_total, battle_total, assist_total,
    donate_total, power_value, group_name.
    Returns the new upload id.
    """
    members = list(members)
    member_count = len(members)
    if member_count == 0:
        raise ValueError("成员数据为空，无法插入")

    conn = get_connection(cfg)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO uploads (user_openid, ts, member_count) VALUES (%s, %s, %s)",
                (user_openid, ts, member_count),
            )
            upload_id = cur.lastrowid
            cur.executemany(
                """
                INSERT INTO upload_members (
                    upload_id, member_name, contrib_rank, contrib_total, battle_total,
                    assist_total, donate_total, power_value, group_name
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                [
                    (
                        upload_id,
                        m["member_name"],
                        m.get("rank"),
                        m["contrib_total"],
                        m["battle_total"],
                        m["assist_total"],
                        m["donate_total"],
                        m["power_value"],
                        m["group_name"],
                    )
                    for m in members
                ],
            )
        conn.commit()
        return int(upload_id)
    finally:
        conn.close()


def list_uploads_by_user(cfg: Mapping[str, Any], user_openid: str) -> list[dict[str, Any]]:
    conn = get_connection(cfg)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, ts, member_count, created_at FROM uploads WHERE user_openid=%s ORDER BY ts DESC",  # noqa: E501
                (user_openid,),
            )
            rows = cur.fetchall()
        return list(rows)
    finally:
        conn.close()


def ensure_user_exists(cfg: Mapping[str, Any], openid: str) -> None:
    conn = get_connection(cfg)
    try:
        with conn.cursor() as cur:
            cur.execute("INSERT IGNORE INTO users (openid) VALUES (%s)", (openid,))
        conn.commit()
    finally:
        conn.close()


def upload_exists(cfg: Mapping[str, Any], user_openid: str, ts) -> bool:
    conn = get_connection(cfg)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM uploads WHERE user_openid=%s AND ts=%s LIMIT 1",
                (user_openid, ts),
            )
            row = cur.fetchone()
            return row is not None
    finally:
        conn.close()


def delete_upload_by_id(cfg: Mapping[str, Any], user_openid: str, upload_id: int) -> bool:
    """Delete a single upload owned by the user. Returns True if deleted."""
    conn = get_connection(cfg)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM uploads WHERE id=%s AND user_openid=%s LIMIT 1",
                (int(upload_id), user_openid),
            )
            affected = cur.rowcount
        conn.commit()
        return affected > 0
    finally:
        conn.close()


def get_upload_with_members(cfg: Mapping[str, Any], user_openid: str, upload_id: int) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """Return upload metadata and its members if owned by user; else (None, [])."""
    conn = get_connection(cfg)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, ts, member_count, created_at FROM uploads WHERE id=%s AND user_openid=%s LIMIT 1",
                (int(upload_id), user_openid),
            )
            upload_row = cur.fetchone()
            if not upload_row:
                return None, []
            cur.execute(
                """
                SELECT member_name, contrib_rank, contrib_total, battle_total, assist_total,
                       donate_total, power_value, group_name
                FROM upload_members WHERE upload_id=%s ORDER BY battle_total DESC, member_name ASC
                """,
                (int(upload_id),),
            )
            members = cur.fetchall() or []
        return upload_row, list(members)
    finally:
        conn.close()


def get_member_history(cfg: Mapping[str, Any], user_openid: str, member_name: str) -> list[dict[str, Any]]:
    """Return time series entries for a specific member owned by the user ordered by upload ts."""
    conn = get_connection(cfg)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    u.id AS upload_id,
                    u.ts,
                    u.created_at,
                    u.member_count,
                    m.member_name,
                    m.contrib_rank,
                    m.contrib_total,
                    m.battle_total,
                    m.assist_total,
                    m.donate_total,
                    m.power_value,
                    m.group_name
                FROM uploads AS u
                JOIN upload_members AS m ON m.upload_id = u.id
                WHERE u.user_openid = %s AND m.member_name = %s
                ORDER BY u.ts ASC, u.id ASC
                """,
                (user_openid, member_name),
            )
            rows = cur.fetchall() or []
        return list(rows)
    finally:
        conn.close()
