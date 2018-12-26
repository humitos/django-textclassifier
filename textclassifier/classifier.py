"""Text classification using Naive Bayes classifier

This classifier relies on :py:mod:`sklearn` for feature extraction and
classification.
"""

import json
import logging

from sklearn.feature_extraction.text import CountVectorizer
from sklearn.naive_bayes import MultinomialNB

from .constants import SPAM
from .models import TrainingData

log = logging.getLogger(__name__)


class NaiveBayesClassifier(object):
    """Naive Bayesian classifier with per-field database storage

    This classifier uses a table for storing training data on each field.
    """

    def __init__(self, app_label, model, field_name):
        self.app_label = app_label
        self.model = model
        self.field_name = field_name
        self.training_data = []

    def load(self):
        try:
            data_obj = TrainingData.objects.get(
                app_label=self.app_label,
                model=self.model,
                field_name=self.field_name
            )
            self.training_data = json.loads(data_obj.data)
        except (TrainingData.DoesNotExist, TypeError):
            self.training_data = []
        except ValueError:
            raise ValueError('The classification data for "%s" is not valid JSON',
                             self.field_name)

    def save(self):
        data = json.dumps(self.training_data)
        stored_data, _ = (TrainingData.objects.get_or_create(
            app_label=self.app_label,
            model=self.model,
            field_name=self.field_name,
        ))
        stored_data.data = data
        stored_data.save()

    def update(self, value, classification=SPAM):
        self.load()
        self.training_data.append((value, classification))
        self.save()

    def classify(self, value, accuracy_threshold=0.95):
        self.load()
        vectorizer = CountVectorizer(min_df=1)
        try:
            sampled = vectorizer.fit_transform(
                [text for (text, _) in self.training_data]
            )
        except (ValueError, TypeError):
            # Training data was not complete or is invalid, return empty result
            return ClassifierResult()
        classifier = MultinomialNB()
        classifier.fit(
            sampled,
            [label for (_, label) in self.training_data]
        )
        class_values = classifier.predict_proba(
            vectorizer.transform([value])
        ).tolist()[0]
        prob = ClassifierResult(
            zip(classifier.classes_.tolist(), class_values),
            accuracy_threshold=accuracy_threshold,
        )
        log.debug(
            'Text Classification: [app_label=%s] [model=%s] [field_name=%s] [value=%s] %s',
            self.app_label,
            self.model,
            self.field_name,
            value,
            prob,
        )
        return prob


class ClassifierResult(dict):

    def is_spam(self, accuracy_threshold=0.95):
        return self.get(SPAM, 0) >= accuracy_threshold

    def is_valid(self, accuracy_threshold=0.95):
        return not self.is_spam(accuracy_threshold)
