"""
Django settings for core project.
"""

from pathlib import Path
import os
from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env file
load_dotenv()

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY')


# SECURITY WARNING: don't run with debug turned on in production!
# Environment detection
IS_PRODUCTION = os.getenv('IS_PRODUCTION', 'False').lower() == 'true'
IS_DOCKER_DEV = os.getenv('IS_DOCKER_DEV', 'False').lower() == 'true'

# Set DEBUG based on environment
if IS_DOCKER_DEV:
    DEBUG = True  # Always True for local Docker development
elif IS_PRODUCTION:
    DEBUG = False  # Always False for production
else:
    DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'  # Fallback to env variable

ALLOWED_HOSTS = ["*"]
# Application definition

INSTALLED_APPS = [
    'daphne',
    'django.contrib.admin',
    'corsheaders',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'surveys',
    'chat',
]

# Add or update these settings
REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',  # This enables the browsable API
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.AllowAny',
    ],
}

# Remove these duplicate static settings
# STATIC_URL = '/static/'
# STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
# STATICFILES_DIRS = [
#     os.path.join(BASE_DIR.parent, 'frontend', 'static'),
# ]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # 添加这行
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'core.middleware.AdminAuthMiddleware',
]

# Remove these duplicate static settings
# STATIC_URL = '/static/'
# STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
# 删除这行
# STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Remove these duplicate static settings
# STATIC_URL = '/static/'
# STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
# STATICFILES_DIRS = [
#     os.path.join(BASE_DIR.parent, 'frontend', 'static'),
# ]

CORS_ALLOWED_ORIGINS = [
    'http://localhost:3000',
    'http://127.0.0.1:3000', 
    'http://localhost:8000',
    'http://127.0.0.1:8000', 
    'https://sowfeehealth.live',
    'https://www.sowfeehealth.live',
    f'http://{os.getenv("EC2_HOST")}',
    f'https://{os.getenv("EC2_HOST")}',
]
CORS_ALLOW_CREDENTIALS = True
# 添加 CSRF 配置
CSRF_TRUSTED_ORIGINS = [
    'https://localhost',
    'https://127.0.0.1',
    'http://localhost',
    'http://127.0.0.1',
    f'http://{os.getenv("EC2_HOST")}',
    f'https://{os.getenv("EC2_HOST")}',
    'http://localhost:8000',
    'http://127.0.0.1:8000',
    'http://localhost:3000',
    'http://127.0.0.1:3000',
    'http://sowfeehealth.live',        
    'http://www.sowfeehealth.live', 
    'https://sowfeehealth.live',
    'http://www.sowfeehealth.live',
    'https://www.sowfeehealth.live',
    'https://sowfeehealth.live/',
    'https://www.sowfeehealth.live/'      
]

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR.parent, 'frontend', 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.1/ref/settings/#databases

# Load .env file
load_dotenv()

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('POSTGRES_DB'),  
        'USER': os.getenv('POSTGRES_USER'),
        'PASSWORD': os.getenv('POSTGRES_PASSWORD'),
        'HOST': os.getenv('POSTGRES_HOST', 'db'),  # 'db' is the service name in Docker
        'PORT': os.getenv('POSTGRES_PORT', '5432'),
        'CONN_MAX_AGE': 60,  # Connection age
        'ATOMIC_REQUESTS': True,  # Every HTTP request in a transaction
    }
}


'''DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'Surveys',  # Replace with your actual database name
        'USER': 'Sowfee',        
        'PASSWORD': 'Health123',  
        'HOST': 'db',   #This is the service name for docker-compose.yaml
        'PORT': '3306',        # Default MySQL port
        'OPTIONS': {
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'"
        }
    }
}'''


# Password validation
# https://docs.djangoproject.com/en/5.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.1/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.1/howto/static-files/

# Static file settings
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_DIRS = [
    os.path.join(BASE_DIR.parent, 'frontend', 'static'),
]
# Default primary key field type
# https://docs.djangoproject.com/en/5.1/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTH_USER_MODEL = 'surveys.User'


# Add logging configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console':{
            'level':'INFO',
            'class':'logging.StreamHandler',
        },
    },
    'loggers': {
        'surveys': {
            'handlers': ['console'],
            'level': 'INFO',  # Changed from DEBUG to INFO
        },
        'django': {
            'handlers': ['console'],
            'level': 'WARNING',  # Changed from INFO to WARNING
        },
    }
}


# Cookie settings based on environment
COOKIE_DOMAIN = '.sowfeehealth.live' if IS_PRODUCTION else None
COOKIE_SECURE = IS_PRODUCTION

# Session cookie settings
SESSION_COOKIE_DOMAIN = COOKIE_DOMAIN
SESSION_COOKIE_SECURE = COOKIE_SECURE
#SESSION_COOKIE_NAME = 'auth_token'

REDIS_HOST = os.getenv('REDIS_HOST', 'redis')  # Default to your container name
REDIS_PORT = os.getenv('REDIS_PORT', '6379')

# settings.py
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': f'redis://{REDIS_HOST}:{REDIS_PORT}/1',
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'CONNECTION_POOL_KWARGS': {
                'max_connections': 20,
                'retry_on_timeout': True,
            },
            'SERIALIZER': 'django_redis.serializers.json.JSONSerializer',
            'COMPRESSOR': 'django_redis.compressors.zlib.ZlibCompressor',
        },
        'KEY_PREFIX': 'sowfee_cache',
        'TIMEOUT': 1800,  # 30 minutes default timeout
    }
}

# Optional: Use Redis for sessions as well
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'default'

CELERY_BROKER_URL = f'redis://{REDIS_HOST}:{REDIS_PORT}/0'
CELERY_RESULT_BACKEND = f'redis://{REDIS_HOST}:{REDIS_PORT}/0'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

ASGI_APPLICATION = "core.asgi.application"

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [(os.environ.get("REDIS_HOST", "127.0.0.1"), 
                       int(os.environ.get("REDIS_PORT", 6379)))],
        },
    }
}
