from abc import ABC, abstractmethod
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class TimestampMixin:
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now,
                        onupdate=datetime.now, nullable=False)


class BaseEntity(Base, TimestampMixin):
    __abstract__ = True

    id = Column(Integer, primary_key=True, index=True)

    def update_timestamp(self):
        self.updated_at = datetime.now()

    def __repr__(self) -> str:
        class_name = self.__class__.__name__
        attributes = []

        for column in self.__table__.columns:
            value = getattr(self, column.name)
            attributes.append(f'{column.name}={value}')

        return f'{class_name}({", ".join(attributes)})'
