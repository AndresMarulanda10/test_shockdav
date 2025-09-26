"""
Configuración centralizada para la aplicación Bitget Orders API.
"""

import os
from dotenv import load_dotenv
from typing import Dict, Any

load_dotenv()

class Config:
    """Configuración de la aplicación"""

    # AWS Configuration
    AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
    AWS_DEFAULT_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-2")
    COORD_LAMBDA_NAME = os.getenv("COORD_LAMBDA_NAME")

    # MySQL Database Configuration
    MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
    MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
    MYSQL_USER = os.getenv("MYSQL_USER", "root")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
    MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "bitget_orders")
    MYSQL_CHARSET = os.getenv("MYSQL_CHARSET", "utf8mb4")

    # Database URL for SQLAlchemy
    DATABASE_URL = os.getenv("DATABASE_URL")

    # Bitget API Configuration (para referencia futura)
    BITGET_API_KEY = os.getenv("BITGET_API_KEY")
    BITGET_API_SECRET = os.getenv("BITGET_API_SECRET")
    BITGET_PASSPHRASE = os.getenv("BITGET_PASSPHRASE")

    # Logging Configuration
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    # API Configuration
    API_TITLE = "Bitget Orders API"
    API_VERSION = "1.0.0"
    API_DESCRIPTION = "API para gestionar órdenes de Bitget con integración a base de datos MySQL"

    @classmethod
    def validate_required_config(cls) -> Dict[str, Any]:
        """
        Valida que todas las configuraciones requeridas estén presentes.

        Returns:
            Diccionario con el estado de validación y errores si los hay
        """
        errors = []
        warnings = []

        # Validar AWS
        if not cls.COORD_LAMBDA_NAME:
            errors.append("COORD_LAMBDA_NAME no está configurada")

        if not cls.AWS_ACCESS_KEY_ID:
            warnings.append("AWS_ACCESS_KEY_ID no está configurada")

        if not cls.AWS_SECRET_ACCESS_KEY:
            warnings.append("AWS_SECRET_ACCESS_KEY no está configurada")

        # Validar Database
        if not cls.DATABASE_URL:
            errors.append("DATABASE_URL no está configurada")

        if not cls.MYSQL_PASSWORD:
            warnings.append("MYSQL_PASSWORD no está configurada")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "config_summary": {
                "aws_region": cls.AWS_DEFAULT_REGION,
                "lambda_name": cls.COORD_LAMBDA_NAME,
                "mysql_host": cls.MYSQL_HOST,
                "mysql_port": cls.MYSQL_PORT,
                "mysql_database": cls.MYSQL_DATABASE,
                "log_level": cls.LOG_LEVEL
            }
        }

    @classmethod
    def get_database_config(cls) -> Dict[str, Any]:
        """Obtiene la configuración de base de datos"""
        return {
            "host": cls.MYSQL_HOST,
            "port": cls.MYSQL_PORT,
            "user": cls.MYSQL_USER,
            "password": cls.MYSQL_PASSWORD,
            "database": cls.MYSQL_DATABASE,
            "charset": cls.MYSQL_CHARSET,
            "url": cls.DATABASE_URL
        }

    @classmethod
    def get_aws_config(cls) -> Dict[str, Any]:
        """Obtiene la configuración de AWS"""
        return {
            "access_key_id": cls.AWS_ACCESS_KEY_ID,
            "secret_access_key": cls.AWS_SECRET_ACCESS_KEY,
            "region": cls.AWS_DEFAULT_REGION,
            "lambda_name": cls.COORD_LAMBDA_NAME
        }

# Instancia global de configuración
config = Config()

# Validar configuración al importar
validation_result = config.validate_required_config()
if not validation_result["valid"]:
    print("Errores de configuración encontrados:")
    for error in validation_result["errors"]:
        print(f"   {error}")

    if validation_result["warnings"]:
        print("Advertencias de configuración:")
        for warning in validation_result["warnings"]:
            print(f"   {warning}")

    print("\nRevisa tu archivo .env y asegúrate de que todas las variables estén configuradas.")
else:
    print("Configuración validada correctamente")
