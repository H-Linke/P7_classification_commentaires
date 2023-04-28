# Fichier servant à effectuer des tests

#######################
#       Imports       #
#######################
import os
import pandas as pd
from Production.python.pretraitement import normalisation_texte

#######################
#      Variables      #
#######################

source = os.getcwd()
comm = "{}/Production/ressources/commentaire.csv".format(source)
comm_label = "{}/Production/ressources/commentaire_labellise.csv".format(source)

data_label_brut = pd.read_csv(comm_label, sep=",", header=None,
                              names=["target", 'ids', 'date', 'flag', 'user', 'text'],
                              on_bad_lines='skip', encoding_errors='ignore',
                              encoding="ISO-8859-1")

data_label = data_label_brut[["target", "text"]]

data = pd.read_csv(comm,
                   squeeze=True,
                   names=["text"],
                   on_bad_lines='skip', encoding_errors='ignore',
                   encoding="ISO-8859-1")


#######################
#      Fonctions      #
#######################

def test_normalisation_texte():
    data_clean = normalisation_texte(data)

    print(data_clean.sample(5))


def test_dev():
    print(data)
