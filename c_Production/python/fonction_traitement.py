# Script contenant les fonctions utiles pour appliquer le nettoyage et formatage des données textuelles

#######################
#       Imports       #
#######################

import os
import re
import contractions
import tensorflow as tf
import tensorflow_hub as hub
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import tensorflow_text as text
import streamlit as st
import nltk
from gensim.models import KeyedVectors
import joblib
import mlflow

nltk.download('punkt')
nltk.download("wordnet")
nltk.download('omw-1.4')
from nltk.tokenize import word_tokenize
from nltk.stem import WordNetLemmatizer

from python.constantes import sample_abbr, emoticons_dict, stop_words


#######################
#      Fonctions      #
#######################

@st.cache_data
def load_data(file):
    """
    Cette fonction charge un fichier CSV dans une série pandas
    :param file: fichier CSV
    :return: Série pandas
    """
    return pd.read_csv(file,
                       squeeze=True,
                       names=["tweet"],
                       on_bad_lines='skip', encoding_errors='ignore',
                       encoding="ISO-8859-1")


def clean_text(comment):
    """
    Cette fonction prend un commentaire en paramètre et le renvoie normalisé
    :param comment: commentaire sous forme de chaîne de caractères
    :return: commentaire normalisé
    """
    # On met tout en minuscules
    comment = comment.lower()

    # On supprime les formes contractées du texte pour uniformiser le format du texte avec la forme décontractée
    comment = contractions.fix(comment)

    # Remplacement des smiley par du texte
    comment = " ".join([emoticons_dict.get(word, word) for word in comment.split()])

    # Remplacement des abbréviations du texte
    comment = " ".join([sample_abbr.get(word, word) for word in comment.split()])

    # Remplacement de certaines parties du texte tels que les utilisateurs, les liens, les mentions
    comment = re.sub(r'@\w+', 'AT_USER', comment)
    comment = re.sub(r'https?://\S+', 'URL', comment)
    comment = re.sub(r'#([^\s]+)', r'\1', comment)
    comment = re.sub(r'[\s]+', ' ', comment)
    comment = re.sub(r'[^a-zA-Z_]', ' ', comment)

    # Remplacement des suites de caractères répétées
    comment = re.compile(r"(.)\1{2,}").sub(r"\1\1", comment)

    # Correction des fautes d'orthographes
    comment = ''.join(comment)

    return comment


def lemmatize_text(comment):
    """
    Cette fonction lemmatise le commente
    :param comment: commentaire
    :return: commentaire lemmatisé
    """
    # Lemmatise
    lemmatizer = WordNetLemmatizer()
    return [lemmatizer.lemmatize(word) for word in comment]


@st.cache_data
def normalisation_texte(data):
    """
    Cette fonction prend en entrée un DataFrame pandas contenant au moins les colonnes target et text et renvoie
    Un DataFrame nettoyé et normalisé.

    :param data: DataFrame pandas contenant les commentaires et leur label
    :return: DataFrame pandas avec les commentaires nettoyés
    """

    data = data.apply(clean_text) \
        .apply(word_tokenize) \
        .apply(lemmatize_text) \
        .apply(lambda comm: [word for word in comm if word not in stop_words]) \
        .apply(lambda x: ["COMMENTAIRE_INSIGNIFIANT"] if x == [] else x) \
        .apply(lambda x: ' '.join(x))

    return data


@st.cache_resource
def model_bert():
    """
    Cette fonction charge le modèle de classication bert préalablement entraîné

    :return: modèle bert
    """
    source = os.getcwd()
    weights_path = "{}/c_Production/model_bert/poids_bert_class_output_v2.npy".format(source)
    # Créer le modèle BERT
    bert_preprocess = hub.KerasLayer("https://tfhub.dev/tensorflow/bert_en_uncased_preprocess/3",
                                     name="bert_preprocess")
    bert_encoder = hub.KerasLayer("https://tfhub.dev/tensorflow/bert_en_uncased_L-12_H-768_A-12/4", name="bert_encoder")
    text_input = tf.keras.layers.Input(batch_size=32, shape=(), dtype=tf.string, name='text')
    preprocessed_text = bert_preprocess(text_input)
    outputs = bert_encoder(preprocessed_text)
    l = tf.keras.layers.Dropout(0.1, name="dropout")(outputs['pooled_output'])

    # Ajouter la dernière couche au modèle
    output_layer = tf.keras.layers.Dense(1, activation='sigmoid', name="output")
    l = output_layer(l)

    # Charger les poids de la dernière couche depuis le fichier
    output_weights = np.load(weights_path, allow_pickle=True)
    output_layer.set_weights(output_weights)

    model = tf.keras.Model(inputs=[text_input], outputs=[l])

    return model


@st.cache_resource
def get_prediction(_model, data_clean):
    """
    Cette fonction fait appel à la méthode prédict d'un modèle tensorflow et le renvoie

    :param _model: modèle tensorflow
    :param data_clean: Serie panda ou liste de donnée prête à entrer dans le modèle
    :return: prédiction appel à la méthode predict du modèle
    """
    return _model.predict(data_clean)


@st.cache_data
def pie_chart(res, seuil):
    """
    Cette fonction sert à afficher un diagramme à cammenbert avec  les prédictions positives et négatives
    """

    # Calculer le nombre de commentaires positifs et négatifs
    nb_positif = (res >= seuil).sum()
    nb_negatif = (res < seuil).sum()

    # Créer le diagramme à secteurs
    labels = ['Positif', 'Negatif']
    sizes = [nb_positif, nb_negatif]
    colors = ['green', 'red']
    explode = (0.1, 0)  # explode 1st slice
    fig1, ax1 = plt.subplots()
    ax1.pie(sizes, explode=explode, labels=labels, colors=colors, autopct='%1.1f%%', startangle=90)
    # Equal aspect ratio ensures that pie is drawn as a circle
    ax1.axis('equal')
    plt.title("Répartition des commentaires")
    plt.show()

    # Afficher le diagramme à secteurs dans Streamlit
    st.pyplot(fig1)


@st.cache_resource
def transform_comments_to_vectors(bad_buzz, vectors_path):
    """
    Transforme les commentaires en vecteurs à l'aide de vecteurs Word2Vec pré-enregistrés.

    :param bad_buzz: Serie pandas composé des colonnes
    :param vectors_path: Chemin vers les vecteurs Word2Vec pré-enregistrés
    :return: DataFrame correspondant à la matrice composée des vecteurs correspondant à chaque commentaire
    """
    bad_buzz = bad_buzz.apply(lambda x: x.split(" "))

    # Charger les vecteurs Word2Vec pré-enregistrés
    word_vectors = KeyedVectors.load(vectors_path, mmap='r')

    # Filtrer les mots selon les vecteurs Word2Vec
    bad_buzz = bad_buzz.apply(lambda words: [word for word in words if word in word_vectors])

    # Remplacer les commentaires vides par un vecteur vide
    bad_buzz = bad_buzz.apply(lambda words: words if len(words) > 0 else ['<empty_comment>'])

    # Enregistrement des vecteurs de chaque commentaire
    bad_buzz_word2vec = bad_buzz.apply(lambda words: np.mean([word_vectors[word] for word in words], axis=0))

    bad_buzz_word2vec = bad_buzz_word2vec.apply(pd.Series)

    return bad_buzz_word2vec


@st.cache_resource
def chargement_modeles_foret_aleatoire(path_source):
    """
    Cette fonction charge et renvoie les différents modèles nécessaires au traitement des données par la foret aléatoire
        - modèle de Standardistion
        - modèle d'ACP
        - modèle de forêt aléatoire

    :param path_source: chemin vers le répertoire base
    :return: les 3 modèles
    """

    scaler = joblib.load("{}/b_Analyse/gestion_modeles/mlruns/models/RF_dependency/scaler.joblib".format(path_source))
    pca = joblib.load("{}/b_Analyse/gestion_modeles/mlruns/models/RF_dependency/pca.joblib".format(path_source))
    random_forest = mlflow.sklearn.load_model(
        "{}/b_Analyse/gestion_modeles/mlruns/0/1166531aed2d4a698a1edc9b673381dc"
        "/artifacts/foret_aleatoire".format(path_source))

    return scaler, pca, random_forest



#################################################################################
#################################################################################
#################################################################################
#################################################################################
#################################################################################


if __name__ == "__main__":
    vectors_path = r"C:\Users\lnkhe\PycharmProjects\P7_classification_commentaires\b_Analyse\gestion_modeles\mlruns\models\Word2Vec\word2vec.wordvectors"
    word_vectors = KeyedVectors.load(vectors_path, mmap='r')

    # print(word_vectors["other"])

    comments = [
        "this is a great product",
        "I love the quality of this item",
        "the customer service was excellent",
        "I had a terrible experience with this company",
        "the shipping was fast and efficient",
        "the price is too high for what you get",
        "the product arrived damaged",
        "the packaging was well done",
        "the website is user-friendly",
        "the product doesn't work as expected",
        "the",
        ""
    ]
    df = pd.DataFrame({"text": comments})
    print(df)

    df_out = transform_comments_to_vectors(df, vectors_path)
    print(df_out)
