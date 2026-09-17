import pytest
from unittest.mock import patch
from content_os import keys_generation as generation
from keys_keywords import infer_family, topic_opportunities, select_targets

CAPCUT = {'kind': 'product', 'title': 'Capcut Pro For 1 Year', 'url': 'https://keys-shop.in/product/capcut/', 'category': 'AI software'}
FINALCUT = {'kind': 'product', 'title': 'Final Cut Pro', 'url': 'https://keys-shop.in/product/final-cut/', 'category': 'Gemini Advanced'}

@pytest.mark.parametrize('target,wrong,correct', [
    (CAPCUT, 'Claude Pro setup guide', 'CapCut setup guide'),
    (FINALCUT, 'Gemini Advanced buying guide', 'Final Cut editing guide'),
])
def test_wrong_product_retries_once_with_selection(target, wrong, correct):
    with patch.object(generation, '_call_ai', side_effect=[([wrong], 'first'), ([correct], 'second')]) as ai:
        assert generation.generate_topics(target, 1, 'Write about a different product') == ([correct], 'second')
    assert ai.call_count == 2
    initial, retry = [call.args[0] for call in ai.call_args_list]
    assert 'IDENTITY LOCK' in initial
    assert target['title'] in initial and target['url'] in initial
    assert 'CORRECTION' in retry and target['title'] in retry

@pytest.mark.parametrize('target,wrong', [(CAPCUT, 'Claude Pro guide'), (FINALCUT, 'Gemini guide')])
def test_api_rejects_wrong_product_after_retry(target, wrong):
    from keys_app import app
    with patch.object(generation, '_call_ai', return_value=([wrong], 'test')) as ai:
        response = app.test_client().post('/api/generate-topics', json={'target': target, 'count': 1})
    assert response.status_code == 400
    assert 'one corrective retry' in response.json['error']
    assert target['title'] in response.json['error']
    assert 'topics' not in response.json
    assert ai.call_count == 2

@pytest.mark.parametrize('titles', [[], {}, [123], [''], ['CapCut setup', 'Claude Pro setup']])
def test_invalid_or_mixed_set_is_not_exposed(titles):
    with patch.object(generation, '_call_ai', return_value=(titles, 'test')) as ai:
        with pytest.raises(generation.GenerationError):
            generation.generate_topics(CAPCUT)
    assert ai.call_count == 2

@pytest.mark.parametrize('target,titles', [
    (CAPCUT, ['CapCut vs Claude Pro: choosing tools', 'Capcut Pro For 1 Year buying guide']),
    (FINALCUT, ['Final-Cut vs Gemini: workflow differences']),
    ({'kind': 'category', 'title': 'Video Editing'}, ['Video editing software: CapCut vs Final Cut']),
    (None, ['General software buying guide']),
])
def test_valid_topics_and_comparisons_do_not_retry(target, titles):
    with patch.object(generation, '_call_ai', return_value=(titles, 'test')) as ai:
        assert generation.generate_topics(target)[0] == titles
    ai.assert_called_once()

@pytest.mark.parametrize('target', [CAPCUT, FINALCUT])
def test_unlisted_product_does_not_inherit_unrelated_keywords(target):
    assert infer_family('Claude Pro guide', target) == ''
    assert topic_opportunities(target)['product_keywords'] == []
    assert select_targets('Gemini guide', target)['product_keywords'] == []

@pytest.mark.parametrize('name,family', [('Claude Pro For 1 Year', 'Claude Pro'), ('Gemini Advanced', 'Gemini Advanced'), ('Canva Pro', 'Canva Pro')])
def test_existing_keyword_targeting_is_preserved(name, family):
    target = {'title': name}
    assert topic_opportunities(target)['family'] == family
    assert select_targets(name + ' buying guide', target)['product_keywords']

def test_version_numbers_are_part_of_product_identity():
    target = {'title': 'Windows 11 Pro For 1 Year'}
    assert generation._topic_matches_target('Windows 11 setup guide', target)
    assert not generation._topic_matches_target('Windows 10 Pro setup guide', target)


def test_category_rejects_unrelated_product_set():
    target = {'kind': 'category', 'title': 'Video Editing'}
    with patch.object(generation, '_call_ai', return_value=(['Claude Pro guide'], 'test')) as ai:
        with pytest.raises(generation.GenerationError):
            generation.generate_topics(target)
    assert ai.call_count == 2
