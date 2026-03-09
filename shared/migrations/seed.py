#!/usr/bin/env python3
"""
EmbedAI DataHub — 初始化 Seed 脚本

执行内容：
  1. 创建 MinIO bucket（episodes / exports）
  2. 创建默认 Project（含 topic schema 模板）
  3. 创建 admin 账号
  4. （可选）创建示例工程师/标注员账号

用法：
  # 基本用法（使用默认密码，仅限开发环境）
  python seed.py

  # 自定义 admin 密码
  ADMIN_PASSWORD=your_password python seed.py

  # 完整环境变量控制
  DATABASE_URL=... MINIO_ENDPOINT=... ADMIN_EMAIL=... python seed.py

环境变量（均有默认值，可通过 .env 覆盖）：
  DATABASE_URL         postgresql://embedai:embedai_dev@localhost:5432/embedai
  MINIO_ENDPOINT       localhost:9000
  MINIO_ACCESS_KEY     minioadmin
  MINIO_SECRET_KEY     minioadmin123
  ADMIN_EMAIL          admin@embedai.local
  ADMIN_NAME           Admin
  ADMIN_PASSWORD       Admin@2026!         ← 生产环境必须修改
  PROJECT_NAME         Default Project
  CREATE_DEMO_USERS    true                ← false 则跳过示例用户
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone

import bcrypt
import psycopg2
from minio import Minio
from minio.error import S3Error

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DATABASE_URL   = os.environ.get("DATABASE_URL",   "postgresql://embedai:embedai_dev@localhost:5432/embedai")
MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS   = os.environ.get("MINIO_ACCESS_KEY","minioadmin")
MINIO_SECRET   = os.environ.get("MINIO_SECRET_KEY","minioadmin123")

ADMIN_EMAIL    = os.environ.get("ADMIN_EMAIL",    "admin@embedai.local")
ADMIN_NAME     = os.environ.get("ADMIN_NAME",     "Admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Admin@2026!")

PROJECT_NAME   = os.environ.get("PROJECT_NAME",   "Default Project")
CREATE_DEMO    = os.environ.get("CREATE_DEMO_USERS", "true").lower() == "true"

BUCKETS = ["episodes", "exports"]

# ---------------------------------------------------------------------------
# Password hashing  (bcrypt-like via hashlib — avoids extra deps)
# Use passlib/bcrypt in production if gateway uses bcrypt.
# ---------------------------------------------------------------------------

def _hash_password(password: str) -> str:
    """Bcrypt hash — matches golang.org/x/crypto/bcrypt used by the gateway."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


# ---------------------------------------------------------------------------
# MinIO setup
# ---------------------------------------------------------------------------

def setup_minio() -> None:
    print("\n── MinIO ──────────────────────────────────────────────────────")
    _secure_env = os.environ.get("MINIO_SECURE", "").lower()
    if _secure_env in ("true", "1", "yes"):
        secure = True
    elif _secure_env in ("false", "0", "no"):
        secure = False
    else:
        secure = not MINIO_ENDPOINT.startswith("localhost") and not MINIO_ENDPOINT.startswith("127.")
    client = Minio(MINIO_ENDPOINT, access_key=MINIO_ACCESS, secret_key=MINIO_SECRET, secure=secure)

    for bucket in BUCKETS:
        try:
            if client.bucket_exists(bucket):
                print(f"  [skip] bucket '{bucket}' already exists")
            else:
                client.make_bucket(bucket)
                print(f"  [ok]   bucket '{bucket}' created")
        except S3Error as e:
            print(f"  [warn] bucket '{bucket}': {e}", file=sys.stderr)


# ---------------------------------------------------------------------------
# PostgreSQL seed
# ---------------------------------------------------------------------------

def _pg_connect():
    # psycopg2 expects postgresql:// not postgresql+asyncpg://
    url = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    return psycopg2.connect(url)


def seed_database() -> None:
    print("\n── PostgreSQL ─────────────────────────────────────────────────")
    conn = _pg_connect()
    conn.autocommit = False
    cur = conn.cursor()

    try:
        project_id = _seed_project(cur)
        _seed_admin(cur, project_id)
        if CREATE_DEMO:
            _seed_demo_users(cur, project_id)
        conn.commit()
        print("\n  ✓ Database seed committed.")
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def _seed_project(cur) -> str:
    cur.execute("SELECT id FROM projects WHERE name = %s LIMIT 1", (PROJECT_NAME,))
    row = cur.fetchone()
    if row:
        print(f"  [skip] project '{PROJECT_NAME}' already exists  (id={row[0]})")
        return str(row[0])

    project_id = str(uuid.uuid4())
    # Default topic schema: common embodied-robot sensor set
    topic_schema = {
        "required_topics": [
            "/camera/rgb",
            "/joint_states",
        ],
        "topic_frequency": {
            "/camera/rgb":   30.0,
            "/joint_states": 50.0,
            "/imu/data":    200.0,
        },
    }
    cur.execute(
        """
        INSERT INTO projects (id, name, description, topic_schema, created_at)
        VALUES (%s, %s, %s, %s::jsonb, %s)
        """,
        (
            project_id,
            PROJECT_NAME,
            "Auto-created by seed script. Edit topic_schema to match your robot's sensor configuration.",
            str(topic_schema).replace("'", '"'),
            datetime.now(timezone.utc),
        ),
    )
    print(f"  [ok]   project '{PROJECT_NAME}' created  (id={project_id})")
    return project_id


def _seed_admin(cur, project_id: str) -> None:
    cur.execute("SELECT id FROM users WHERE email = %s LIMIT 1", (ADMIN_EMAIL,))
    if cur.fetchone():
        print(f"  [skip] admin '{ADMIN_EMAIL}' already exists")
        return

    user_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO users (id, email, name, hashed_password, role, skill_tags, project_id, is_active, created_at)
        VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, true, %s)
        """,
        (
            user_id,
            ADMIN_EMAIL,
            ADMIN_NAME,
            _hash_password(ADMIN_PASSWORD),
            "admin",
            "[]",
            project_id,
            datetime.now(timezone.utc),
        ),
    )
    print(f"  [ok]   admin '{ADMIN_EMAIL}' created  (id={user_id})")
    if ADMIN_PASSWORD == "Admin@2026!":
        print("  [warn] Using default admin password — change it before going to production!")


def _seed_demo_users(cur, project_id: str) -> None:
    """Create sample engineer and annotator accounts for development."""
    demo_users = [
        {
            "email":    "engineer@embedai.local",
            "name":     "Data Engineer",
            "role":     "engineer",
            "password": "Engineer@2026!",
            "skills":   '["pipeline", "dataset"]',
        },
        {
            "email":    "annotator1@embedai.local",
            "name":     "Annotator One",
            "role":     "annotator_internal",
            "password": "Annotator@2026!",
            "skills":   '["bbox2d", "keypoint", "timeline"]',
        },
        {
            "email":    "outsource1@embedai.local",
            "name":     "Outsource Annotator",
            "role":     "annotator_outsource",
            "password": "Outsource@2026!",
            "skills":   '["bbox2d"]',
        },
    ]

    for u in demo_users:
        cur.execute("SELECT id FROM users WHERE email = %s LIMIT 1", (u["email"],))
        if cur.fetchone():
            print(f"  [skip] demo user '{u['email']}' already exists")
            continue

        user_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO users (id, email, name, hashed_password, role, skill_tags, project_id, is_active, created_at)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, true, %s)
            """,
            (
                user_id,
                u["email"],
                u["name"],
                _hash_password(u["password"]),
                u["role"],
                u["skills"],
                project_id,
                datetime.now(timezone.utc),
            ),
        )
        print(f"  [ok]   demo user '{u['email']}' ({u['role']}) created")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 60)
    print("  EmbedAI DataHub — Seed Script")
    print("=" * 60)
    print(f"  DATABASE : {DATABASE_URL.split('@')[-1]}")   # hide credentials
    print(f"  MINIO    : {MINIO_ENDPOINT}")
    print(f"  ADMIN    : {ADMIN_EMAIL}")
    print(f"  DEMO     : {'yes' if CREATE_DEMO else 'no'}")

    try:
        setup_minio()
    except Exception as e:
        print(f"\n[error] MinIO setup failed: {e}", file=sys.stderr)
        print("  → Is MinIO running? Check MINIO_ENDPOINT.", file=sys.stderr)
        sys.exit(1)

    try:
        seed_database()
    except Exception as e:
        print(f"\n[error] Database seed failed: {e}", file=sys.stderr)
        print("  → Is PostgreSQL running? Did you run 'make migrate' first?", file=sys.stderr)
        sys.exit(1)

    print("\n" + "=" * 60)
    print("  Seed complete. Login credentials:")
    print(f"    Admin    : {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
    if CREATE_DEMO:
        print("    Engineer : engineer@embedai.local / Engineer@2026!")
        print("    Annotator: annotator1@embedai.local / Annotator@2026!")
        print("    Outsource: outsource1@embedai.local / Outsource@2026!")
    print("=" * 60)
    print()


if __name__ == "__main__":
    main()
