"""
Script de inicio para la aplicación Bitget Orders API.
Valida la configuración y dependencias antes de iniciar el servidor.
"""

import sys
import os

# Agregar el directorio padre al path para poder importar los módulos
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import subprocess
from pathlib import Path

def check_dependencies():
    """Verifica que las dependencias estén instaladas"""
    print("Verificando dependencias...")

    required_packages = [
        "fastapi",
        "uvicorn",
        "sqlalchemy",
        "pymysql",
        "boto3",
        "python-dotenv",
        "requests"
    ]

    missing_packages = []

    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            missing_packages.append(package)

    if missing_packages:
        print(f"Faltan las siguientes dependencias: {', '.join(missing_packages)}")
        print("Instálelas con: pip install -r requirements.txt")
        return False

    print("Todas las dependencias están instaladas")
    return True

def check_env_file():
    """Verifica que el archivo .env existe"""
    print("Verificando archivo .env...")

    env_file = Path(".env")
    if not env_file.exists():
        print("Archivo .env no encontrado")
        print("Crea un archivo .env con las variables de entorno necesarias")
        return False

    print("Archivo .env encontrado")
    return True

def validate_config():
    """Valida la configuración usando el módulo de configuración"""
    print("Validando configuración...")

    try:
        from app.core.config import config
        validation = config.validate_required_config()

        if validation["valid"]:
            print("Configuración válida")
            return True
        else:
            print("Configuración inválida:")
            for error in validation["errors"]:
                print(f"   {error}")
            for warning in validation["warnings"]:
                print(f"   {warning}")
            return False

    except Exception as e:
        print(f"Error validando configuración: {str(e)}")
        return False

def check_database():
    """Verifica la conexión a la base de datos"""
    print("Verificando conexión a base de datos...")

    try:
        from app.models.database import engine
        from sqlalchemy import text

        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        print("Conexión a base de datos exitosa")
        return True
    except Exception as e:
        print(f"Error conectando a base de datos: {str(e)}")
        print("Sugerencias:")
        print("   1. Verifica que MySQL esté ejecutándose")
        print("   2. Verifica las credenciales en .env")
        print("   3. Ejecuta: python scripts/init_db.py")
        return False

def initialize_database():
    """Inicializa la base de datos si es necesario"""
    print("Verificando tablas de base de datos...")

    try:
        from app.models.database import create_tables
        create_tables()
        print("Tablas de base de datos verificadas/creadas")
        return True
    except Exception as e:
        print(f"Error inicializando base de datos: {str(e)}")
        return False

def start_server():
    """Inicia el servidor FastAPI"""
    print("\nIniciando servidor FastAPI...")
    print("Servidor disponible en: http://localhost:8000")
    print("Documentación en: http://localhost:8000/docs")
    print("ReDoc en: http://localhost:8000/redoc")
    print("\nPara detener el servidor, presiona Ctrl+C\n")

    try:
        import uvicorn
        uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
    except KeyboardInterrupt:
        print("\nServidor detenido por el usuario")
    except Exception as e:
        print(f"Error iniciando servidor: {str(e)}")

def main():
    """Función principal"""
    print("Bitget Orders API - Inicio de aplicación")
    print("="*50)

    # Lista de verificaciones
    checks = [
        ("Dependencias", check_dependencies),
        ("Archivo .env", check_env_file),
        ("Configuración", validate_config),
        ("Base de datos", check_database),
        ("Inicialización BD", initialize_database)
    ]

    # Ejecutar verificaciones
    all_passed = True
    for check_name, check_func in checks:
        if not check_func():
            all_passed = False
            break
        print()  # Línea en blanco entre verificaciones

    if all_passed:
        print("Todas las verificaciones pasaron correctamente\n")
        start_server()
    else:
        print("\nFalló alguna verificación. Corrige los errores antes de continuar.")
        print("\nPara más detalles, ejecuta: python test_app.py")
        sys.exit(1)

if __name__ == "__main__":
    main()
