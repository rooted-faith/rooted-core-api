"""Devotion editorial pool, translations, and calendar schedule."""

import sqlalchemy as sa
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB, UUID

from portal.libs.database.orm import ModelBase
from portal.models.app import AppUser
from portal.models.mixins import AuditCreatedAtMixin, AuditUpdatedAtMixin
from portal.models.system_locale import SystemLocale


class Devotion(ModelBase, AuditCreatedAtMixin, AuditUpdatedAtMixin):
    __tablename__ = "devotions"
    __extra_table_args__ = (sa.CheckConstraint("status IN ('draft', 'ready')", name="devotion_status"), {"comment": "Devotion editorial content pool"})

    passage_start = Column(sa.String(50), nullable=False, comment="First bible.verses passage_id")
    passage_end = Column(sa.String(50), nullable=False, comment="Last bible.verses passage_id")
    status = Column(sa.String(10), nullable=False, server_default="draft", index=True)


class DevotionTranslation(ModelBase, AuditCreatedAtMixin, AuditUpdatedAtMixin):
    __tablename__ = "translations"
    __extra_table_args__ = (sa.UniqueConstraint("devotion_id", "locale_id"), {"comment": "Locale-specific authored Devotion content"})

    devotion_id = Column(UUID, sa.ForeignKey(Devotion.id, ondelete="CASCADE"), nullable=False, index=True)
    locale_id = Column(UUID, sa.ForeignKey(SystemLocale.id), nullable=False, index=True)
    reflect = Column(JSONB, nullable=False, comment="Ordered reflection prompt strings")
    apply = Column(sa.Text, nullable=False, comment="Today's application")
    pray = Column(sa.Text, nullable=False, comment="Prayer")


class DevotionDailyLessonSchedule(ModelBase, AuditCreatedAtMixin, AuditUpdatedAtMixin):
    __tablename__ = "daily_lesson_schedule"
    __extra_table_args__ = ({"comment": "One scheduled Devotion per calendar date"},)

    date = Column(sa.Date, nullable=False, unique=True)
    devotion_id = Column(UUID, sa.ForeignKey(Devotion.id), nullable=False, index=True)


class EncounterDay(ModelBase, AuditCreatedAtMixin):
    __tablename__ = "encounter_days"
    __extra_table_args__ = (sa.UniqueConstraint("user_id", "date"), {"comment": "One private Encounter day per End user and date"})

    user_id = Column(UUID, sa.ForeignKey(AppUser.id, ondelete="CASCADE"), nullable=False, index=True)
    date = Column(sa.Date, nullable=False, index=True)


class LessonNote(ModelBase, AuditCreatedAtMixin, AuditUpdatedAtMixin):
    __tablename__ = "lesson_notes"
    __extra_table_args__ = (sa.UniqueConstraint("user_id", "date"), {"comment": "One private lesson note per End user and date"})

    user_id = Column(UUID, sa.ForeignKey(AppUser.id, ondelete="CASCADE"), nullable=False, index=True)
    date = Column(sa.Date, nullable=False, index=True)
    body = Column(sa.Text, nullable=True)
    reflect_answers = Column(JSONB, nullable=False, server_default=sa.text("'[]'::jsonb"), comment="Ordered optional reflection answers")


class EncounterStreak(ModelBase, AuditUpdatedAtMixin):
    __tablename__ = "encounter_streaks"
    __extra_table_args__ = ({"comment": "Stored longest streak and current-streak write cache (ADR 0012)"},)

    user_id = Column(UUID, sa.ForeignKey(AppUser.id, ondelete="CASCADE"), nullable=False, unique=True)
    longest_streak = Column(sa.Integer, nullable=False, server_default="0")
    current_streak_length = Column(sa.Integer, nullable=False, server_default="0")
    last_encounter_date = Column(sa.Date, nullable=True)
