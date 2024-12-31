import stat
from logging import handlers
import os

class GroupWriteRotatingFileHandler(handlers.RotatingFileHandler):  

    """
    For use in Django, in settings.py
    
    from .custom_logging import GroupWriteRotatingFileHandler

    logging.handlers.GroupWriteRotatingFileHandler = GroupWriteRotatingFileHandler

    LOGGING = {
        ...,
        'handlers': {
            'file_app': {
                'level': 'INFO',
                'class': "logging.handlers.GroupWriteRotatingFileHandler",
                'filename': os.path.join(LOG_FOLDER, 'mylog.log'),
                'maxBytes': 1024*1024*5,  # 5 MB
                'backupCount': 5,
                'formatter': 'verbose'
            },
        ...
    """  
    
    def doRollover(self):
        """
        Override base class method to make the new log file group writable.
        """
        # Rotate the file first.
        handlers.RotatingFileHandler.doRollover(self)

        # Add group write to the current permissions.
        log_file_permissions(self.baseFilename)


def log_file_permissions(log_file):
    currMode = os.stat(log_file).st_mode
    try:
        os.chmod(log_file, currMode | stat.S_IWGRP)
    except PermissionError:
        ...
