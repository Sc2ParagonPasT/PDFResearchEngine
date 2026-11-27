import unittest
from repositories_v05 import Document
from relevance_v051 import Policy as PreviousPolicy
from context_v052 import Policy,query_terms,intent,clauses,CONCEPTS
from benchmark_v052 import CASES,LIVE_TOPICS

def doc(title,**kw):
    return Document(title,'https://zenodo.org/example.pdf','Zenodo',**kw)
class ContextTests(unittest.TestCase):
    def test_benchmark_balanced(self):
        for q,positive,related,negative in CASES:
            with self.subTest(query=q):
                p=Policy(q)
                a,b,c=(p.evaluate(doc(t)) for t in (positive,related,negative))
                self.assertIsNotNone(a,(q,positive))
                self.assertIsNotNone(b,(q,related))
                self.assertIsNone(c,(q,negative))
                self.assertGreaterEqual(a.score,b.score,(q,a,b))
    def test_benchmark_focused(self):
        for q,positive,_,negative in CASES:
            with self.subTest(query=q):
                p=Policy(q,'Focused');self.assertIsNotNone(p.evaluate(doc(positive)));self.assertIsNone(p.evaluate(doc(negative)))
    def test_original_live_false_positives(self):
        q='Hatred in Society'
        unwanted=('Analysis of the thought and art of Bai Juyi’s "Song of Long Hatred"',
            'Does harboring hostility hurt? Associations between hostility and pulmonary function in the Coronary Artery Risk Development in Adults (CARDIA) study',
            'Longitudinal association of serum carotenoids and tocopherols with hostility: The CARDIA study',
            'Social support and health behavior in hostile black and white men and women in CARDIA',
            'Fairy Tales in Modern Society')
        for t in unwanted:
            with self.subTest(title=t):
                self.assertIsNone(Policy(q,'Balanced').evaluate(doc(t)))
                self.assertIsNone(Policy(q,'Focused').evaluate(doc(t)))
                m=Policy(q,'Exploratory').evaluate(doc(t))
                if m:self.assertLessEqual(m.score,48)
        for t in ('Spread of Religious Hatred through Digital Media in Pakistan','Clerical Counter-Narratives to Online Hate Speech on Social Media','Collective hatred and societal conflict'):
            self.assertIsNotNone(Policy(q).evaluate(doc(t)))
    def test_legitimate_interdisciplinary_context(self):
        t='Hostility and pulmonary function in young adults'
        self.assertIsNotNone(Policy('Medical hostility').evaluate(doc(t)))
        self.assertIsNotNone(Policy('Hatred in literature').evaluate(doc('Literary representations of hatred in poetry')))
        t='Collective hatred and social conflict: cardiovascular outcomes'
        self.assertIsNotNone(Policy('Hatred in Society').evaluate(doc(t)))
    def test_nearby_context_not_global_bag_of_words(self):
        p=Policy('Hatred in Society')
        self.assertIsNone(p.evaluate(doc('Unrelated findings',description='Hostility predicts pulmonary function. Society has many institutions.')))
        self.assertIsNotNone(p.evaluate(doc('Group attitudes',description='Collective hatred predicts social conflict.')))
        self.assertIsNone(p.evaluate(doc('Society',query='collective hatred')))
    def test_contextual_expansion_and_compounds(self):
        terms=query_terms('Hatred in Society','Balanced')
        self.assertIn('prejudice society',terms)
        self.assertNotIn('society',terms)
        self.assertTrue(all('banking' in t.lower() or 'bank' in t.lower() or 'credit institutions' in t.lower() or 'financial intermediation' in t.lower() for t in query_terms('CIA banking')))
        self.assertEqual(len(intent('Central Banking').concepts),1)
        self.assertEqual(len(intent('Remote Viewing').concepts),1)
        self.assertGreaterEqual(len(CONCEPTS),60)
    def test_metadata_and_filters(self):
        p=Policy('Hatred in Society','Balanced',clauses('social conflict, history'),clauses('fairy tales'))
        self.assertIsNotNone(p.evaluate(doc('Hatred and social conflict',description='History of a conflict.')))
        self.assertIsNone(p.evaluate(doc('Hatred and social conflict',description='History of fairy tales.')))
        self.assertIsNone(Policy('Hatred in Society').evaluate(doc('Society and culture',query='hatred')))
    def test_unknown_topics_not_lost(self):
        self.assertIsNotNone(Policy('trapezoidal quadrature').evaluate(doc('Trapezoidal quadrature and convergence')))
        self.assertIsNone(Policy('trapezoidal quadrature').evaluate(doc('Trapezoidal roofs')))
        self.assertIsNotNone(Policy('society').evaluate(doc('Society and culture')))
        self.assertIsNotNone(Policy('history').evaluate(doc('History of Rome')))
    def test_mode_separation(self):
        q='Hatred in Society';t='Social identity theory'
        self.assertIsNone(Policy(q,'Balanced').evaluate(doc(t)))
        self.assertIsNotNone(Policy(q,'Exploratory').evaluate(doc(t)))
        self.assertIsNone(Policy(q,'Exploratory').evaluate(doc('Fairy tales in society')))
    def test_fixture_scope(self):
        self.assertGreaterEqual(len({x[0] for x in CASES}),20)
        self.assertGreaterEqual(len({q for ts in LIVE_TOPICS.values() for q in ts}),20)
