import sys
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.uic import loadUi

class Saver(QMainWindow):
    def __init__(self):
        super(Saver, self).__init__()
        #  self.setWindowFlags(Qt.FramelessWindowHint)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint) 
        loadUi("ui2/home_aug.ui", self)

        # self.setAttribute(Qt.WA_TranslucentBackground)
      
if __name__ == "__main__":
    # QApplication.setStyle("Fusion")
    app = QApplication(sys.argv)
    saver = Saver()
    saver.show()
    sys.exit(app.exec_())