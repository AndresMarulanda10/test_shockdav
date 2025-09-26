"""Database models and helpers for the project.
This file is defensive: it works even when SQLAlchemy is not installed (useful for quick local checks).
When SQLAlchemy is available and DATABASE_URL is configured, models and helpers are functional.
"""
from datetime import datetime, timezone, timedelta
from app.core.config import config

BOGOTA_TIMEZONE = timezone(timedelta(hours=-5))


def get_bogota_now():
    """Obtiene la fecha y hora actual en zona horaria de Bogotá (UTC-5)"""
    utc_now = datetime.now(timezone.utc)
    return utc_now.astimezone(BOGOTA_TIMEZONE).replace(tzinfo=None)


# Try to import SQLAlchemy; if not present, expose no-op fallbacks so the module can be imported
try:
    from sqlalchemy import Column, Integer, String, DateTime, Text, BigInteger, Float, text, UniqueConstraint
    from sqlalchemy.ext.declarative import declarative_base
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import create_engine
    _HAS_SQLALCHEMY = True
except Exception:
    _HAS_SQLALCHEMY = False
    Column = None
    Integer = String = DateTime = Text = BigInteger = Float = object

    def text(*a, **k):
        return None

    def UniqueConstraint(*a, **k):
        return None

    def declarative_base():
        class _Base:
            pass

        return _Base

    def sessionmaker(*args, **kwargs):
        def _noop_sessionmaker():
            return None

        return _noop_sessionmaker

    def create_engine(*args, **kwargs):
        return None


if _HAS_SQLALCHEMY:
    Base = declarative_base()

    class ExecutionResult(Base):
        """Tabla para almacenar los resultados de las ejecuciones"""
        __tablename__ = "execution_results"

        id = Column(Integer, primary_key=True, autoincrement=True)
        execution_arn = Column(String(255), unique=True, nullable=False, index=True)
        status = Column(String(50), nullable=False)
        total_symbols = Column(Integer)
        total_orders = Column(Integer)
        s3_uri = Column(Text)
        public_url = Column(Text)
        result_data = Column(Text)
        processing_time_seconds = Column(Float)
        created_at = Column(DateTime, default=get_bogota_now)
        updated_at = Column(DateTime, default=get_bogota_now, onupdate=get_bogota_now)


    class Order(Base):
        """Tabla para almacenar las órdenes de trading"""
        __tablename__ = "orders"
        __table_args__ = (
            UniqueConstraint("execution_arn", "order_id", name="u_execution_order"),
        )

        id = Column(Integer, primary_key=True, autoincrement=True)

        # Relación solo por execution_arn (sin FK)
        execution_arn = Column(String(255), nullable=False, index=True)

        # Campos básicos de la orden
        symbol = Column(String(20), nullable=False, index=True)
        order_id = Column(String(50), nullable=False, index=True)

        # Campos de volumen y precio
        size = Column(String(50))
        price = Column(String(50))
        price_avg = Column(String(50))
        base_volume = Column(String(50))
        quote_volume = Column(String(50))

        # Campos de estado y configuración
        status = Column(String(30))
        side = Column(String(20))  # buy/sell/close_long/close_short
        order_type = Column(String(30))  # market/limit
        force = Column(String(20))  # gtc, ioc, etc.

        # Campos específicos de futuros
        leverage = Column(String(10))
        margin_mode = Column(String(30))  # isolated/crossed
        margin_coin = Column(String(20))
        pos_side = Column(String(20))  # long/short
        pos_mode = Column(String(30))  # hedge_mode/one_way_mode
        trade_side = Column(String(30))  # open/close/sell_single/buy_single/close_long/close_short
        reduce_only = Column(String(10))  # YES/NO
        pos_avg = Column(String(50))

        # Campos de costos y ganancias
        fee = Column(String(50))
        total_profits = Column(String(50))

        # Campos de origen y configuración
        client_oid = Column(String(50))
        order_source = Column(String(30))  # pos_loss_market, etc.
        enter_point_source = Column(String(30))  # WEB, API, etc.
        preset_stop_surplus_price = Column(String(50))
        preset_stop_loss_price = Column(String(50))

        # Timestamps (en milliseconds)
        c_time = Column(BigInteger)  # Creation time
        u_time = Column(BigInteger)  # Update time

        # Timestamp de registro en nuestra BD
        created_at = Column(DateTime, default=get_bogota_now)


    class ProcessingLog(Base):
        """Tabla para logs de procesamiento"""
        __tablename__ = "processing_logs"

        id = Column(Integer, primary_key=True, autoincrement=True)
        execution_arn = Column(String(255), nullable=False, index=True)
        level = Column(String(20), nullable=False)  # INFO, ERROR, WARNING
        message = Column(Text, nullable=False)
        details = Column(Text)  # JSON string con detalles adicionales
        created_at = Column(DateTime, default=get_bogota_now)


    # Configuración de la base de datos
    DATABASE_URL = config.DATABASE_URL
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL no está configurada en el archivo .env")

    engine = create_engine(DATABASE_URL, echo=False)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


    def create_tables():
        """Crear todas las tablas en la base de datos"""
        try:
            print("Intentando conectar a la base de datos...")
            print(f"URL: {DATABASE_URL[:50]}..." if DATABASE_URL else "URL no configurada")

            Base.metadata.create_all(bind=engine)
            print("Tablas de base de datos creadas/verificadas correctamente")

            # Verificar conexión con una consulta simple
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
                print("Conexión de prueba exitosa")

            return True
        except Exception as e:
            error_msg = str(e)
            print(f"No se pudo conectar a la base de datos: {error_msg}")
            print(f"Tipo de error: {type(e).__name__}")

            # Diagnóstico específico de errores comunes
            if "Access denied" in error_msg:
                print("Error de autenticación - verifica usuario/contraseña")
            elif "Can't connect to MySQL server" in error_msg:
                print("Error de conexión - verifica que MySQL esté ejecutándose")
            elif "Unknown database" in error_msg:
                print("Base de datos no existe - créala con CREATE DATABASE")

            print("La aplicación continuará funcionando en modo sin base de datos")
            return False


    def get_db_session():
        """Obtener una sesión de base de datos"""
        try:
            session = SessionLocal()
            # Verificar que la sesión funcione con una consulta simple
            session.execute(text("SELECT 1"))
            return session
        except Exception as e:
            print(f"Error al crear sesión de base de datos: {str(e)}")
            print(f"Tipo de error: {type(e).__name__}")
            return None


    def save_execution_result(session, execution_arn: str, status: str, total_symbols: int = 0, total_orders: int = 0, s3_uri: str = None, public_url: str = None, result_data: str = None, processing_time_seconds: float = None):
        """Create and persist an ExecutionResult record. Returns the created ExecutionResult instance.

        The caller is responsible for committing the transaction (session.commit()) if desired.
        """
        er = ExecutionResult(
            execution_arn=execution_arn,
            status=status,
            total_symbols=total_symbols,
            total_orders=total_orders,
            s3_uri=s3_uri,
            public_url=public_url,
            result_data=result_data,
            processing_time_seconds=processing_time_seconds,
        )
        session.add(er)
        try:
            session.flush()
        except Exception:
            session.rollback()
            raise
        return er


    def save_orders_bulk(session, execution_arn: str, orders: list):
        """Bulk insert orders for an execution.

        orders is a list of dict-like objects from Bitget. This function will map common fields to the
        Order model columns. Duplicate (execution_arn, order_id) entries are skipped.
        Returns number of rows inserted.
        """
        if not orders:
            return 0

        mappings = []
        for o in orders:
            if not isinstance(o, dict):
                continue
            order_id = o.get('orderId') or o.get('id') or o.get('order_id')
            symbol = o.get('symbol') or o.get('symbolName') or o.get('instId')
            try:
                c_time = int(o.get('cTime') or o.get('createdAt') or o.get('orderTime') or 0)
            except Exception:
                c_time = None

            mapping = {
                'execution_arn': execution_arn,
                'symbol': symbol,
                'order_id': str(order_id) if order_id is not None else None,
                'size': str(o.get('size') or o.get('quantity') or o.get('filled_qty') or ''),
                'price': str(o.get('price') or ''),
                'price_avg': str(o.get('price_avg') or ''),
                'base_volume': str(o.get('baseVolume') or ''),
                'quote_volume': str(o.get('quoteVolume') or ''),
                'status': o.get('status') or o.get('state') or '',
                'side': o.get('side') or '',
                'order_type': o.get('type') or o.get('orderType') or '',
                'force': o.get('force') or '',
                'leverage': str(o.get('leverage') or ''),
                'margin_mode': o.get('marginMode') or '',
                'margin_coin': o.get('marginCoin') or '',
                'pos_side': o.get('posSide') or '',
                'pos_mode': o.get('posMode') or '',
                'trade_side': o.get('tradeSide') or '',
                'reduce_only': str(o.get('reduceOnly') or ''),
                'pos_avg': str(o.get('posAvg') or ''),
                'fee': str(o.get('fee') or ''),
                'total_profits': str(o.get('totalProfits') or ''),
                'client_oid': o.get('client_oid') or o.get('clientOrderId') or '',
                'order_source': o.get('order_source') or '',
                'enter_point_source': o.get('enter_point_source') or '',
                'preset_stop_surplus_price': str(o.get('preset_stop_surplus_price') or ''),
                'preset_stop_loss_price': str(o.get('preset_stop_loss_price') or ''),
                'c_time': c_time,
                'u_time': None,
            }
            # skip if no order_id or no symbol
            if not mapping['order_id'] or not mapping['symbol']:
                continue
            mappings.append(mapping)

        if not mappings:
            return 0

        inserted = 0
        try:
            # Use bulk insert mappings; unique constraint will raise on duplicates in many DBs.
            session.bulk_insert_mappings(Order, mappings)
            session.flush()
            inserted = len(mappings)
        except Exception:
            # Fallback: try inserting one-by-one to skip duplicates gracefully
            session.rollback()
            inserted = 0
            for m in mappings:
                try:
                    o = Order(**m)
                    session.add(o)
                    session.flush()
                    inserted += 1
                except Exception:
                    session.rollback()
                    continue

        return inserted
else:
    # SQLAlchemy missing: provide safe no-op implementations and simpler helpers
    def create_tables():
        print("[db] SQLAlchemy not installed; create_tables is a no-op")
        return False

    def get_db_session():
        print("[db] SQLAlchemy not installed; get_db_session returns None")
        return None

    def save_execution_result(*args, **kwargs):
        print("[db] SQLAlchemy not installed; save_execution_result is a no-op")
        return None

    def save_orders_bulk(*args, **kwargs):
        print("[db] SQLAlchemy not installed; save_orders_bulk is a no-op")
        return 0



