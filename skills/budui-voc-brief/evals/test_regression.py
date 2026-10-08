#!/usr/bin/env python3
"""关键回归：数据血缘、口径、形态展示、资源完整性与原声去重。"""
import csv
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
PYTHON = sys.executable


class TestVocBriefRegression(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.work = pathlib.Path(self.temp.name)
        self.data = self.work / 'voc.csv'
        headers = ['数据日期', '一级标签', '二级标签', '三级标签', '四级标签', '观点标签', '情感', '内容',
                   '车型', '专营店编码', '专营店名称', '声音ID', '大区', '渠道']
        rows = [
            ['2026-09-01', '产品', '底盘', '轮胎', '轮胎', '爆胎', '好评', '轮胎更换后体验很好。', 'NX8', 'S001', '上海专营店', 'id-1', '华东', 'App'],
            ['2026-09-02', '产品', '底盘', '轮胎', '轮胎', '爆胎', '中性', '请问轮胎爆胎如何处理？', 'NX8', 'S001', '上海专营店', 'id-2', '华东', 'App'],
            ['2026-09-03', '产品', '底盘', '轮胎', '轮胎', '爆胎', '负面', '轮胎爆胎后无法继续行驶，等待救援。', 'N6', 'S002', '北京专营店', 'id-3', '华北', '热线'],
            ['2026-09-04', '产品', '底盘', '轮胎', '轮胎', '爆胎', '负面', '轮胎爆胎后无法继续行驶，等待救援。', 'N6', 'S002', '北京专营店', 'id-4', '华北', '热线'],
        ]
        with self.data.open('w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(rows)
        self.scope = self.work / 'scope.json'
        self.scope.write_text(json.dumps({
            'data_file': str(self.data), 'topic': '轮胎', 'query_raw': '轮胎', 'period': '周',
            'main_scope': {'key': 'l4', 'value': '轮胎', 'phenomenon': ''},
        }, ensure_ascii=False), encoding='utf-8')
        self.stats = self.work / 'stats.json'

    def tearDown(self):
        self.temp.cleanup()

    def run_cmd(self, *args, cwd=ROOT):
        return subprocess.run([PYTHON, *map(str, args)], cwd=cwd, text=True,
                              capture_output=True, encoding='utf-8',
                              env={**os.environ, 'PYTHONUTF8': '1'})

    def test_data_lineage_store_name_and_quote_dedup(self):
        result = self.run_cmd(ROOT / 'scripts' / 'analyze.py', '--scope', self.scope, '--out', self.stats)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        stats = json.loads(self.stats.read_text(encoding='utf-8'))
        self.assertEqual((stats['m2']['positive_n'], stats['m2']['neutral_n'], stats['m2']['negative_n']), (1, 1, 2))
        self.assertNotIn('config', stats['m7'])
        self.assertEqual(stats['m7']['专营店'][0][0], '上海专营店')
        self.assertTrue(all('CSV行=' in row['source_ref'] for row in stats['detail']))
        samples = stats['m8']['samples']
        self.assertEqual(len(samples), 3, samples)
        self.assertTrue(all(len(sample) == 4 and 'CSV行=' in sample[3] for sample in samples))
        self.assertIn('source_file_sha256', stats['trace'])

    def test_poster_has_theme_and_unique_quotes(self):
        self.test_data_lineage_store_name_and_quote_dedup()
        html_file = self.work / 'brief.html'
        result = self.run_cmd(ROOT / 'scripts' / 'render_poster.py', '--stats', self.stats, '--out', html_file)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        page = html_file.read_text(encoding='utf-8')
        self.assertIn(':root{--primary:#F5820B;', page)
        self.assertNotIn('theme-art', page)
        self.assertLess(page.index('集中度分布'), page.index('关键洞察'))
        self.assertGreater(page.index('公域舆情观察'), page.index('代表性客户原声'))
        self.assertIn('本期未启用公域检索', page)
        self.assertNotIn('数据体检与口径说明', page)
        # 正面原声只有一条时，口碑区不重复引用它；整页只出现一次。
        self.assertEqual(page.count('轮胎更换后体验很好。'), 1)

        blue_file = self.work / 'brief-blue.html'
        blue = self.run_cmd(ROOT / 'scripts' / 'render_poster.py', '--stats', self.stats,
                            '--out', blue_file, '--theme', '深海蓝图')
        self.assertEqual(blue.returncode, 0, blue.stderr + blue.stdout)
        blue_page = blue_file.read_text(encoding='utf-8')
        self.assertIn('--primary-head:#EAF4FF', blue_page)
        self.assertIn('--primary-shadow:rgba(40,120,212,.24)', blue_page)
        self.assertIn('linear-gradient(155deg,var(--primary-head) 0%,var(--primary-card) 49%,#FFFFFF 100%)', blue_page)
        self.assertNotIn('rgba(255,251,244', blue_page)
        self.assertNotIn('rgba(245,130,11,.3)', blue_page)

    def test_full_mode_poster_uses_emotion_percentage_parameter(self):
        """正面达到全貌阈值时，三档情感卡片必须可渲染。"""
        self.test_data_lineage_store_name_and_quote_dedup()
        stats = json.loads(self.stats.read_text(encoding='utf-8'))
        stats['m2'].update({
            'n': 13, 'positive_n': 10, 'positive_rate': 76.9,
            'neutral_n': 1, 'neutral_rate': 7.7,
            'negative_n': 2, 'negative_rate': 15.4,
        })
        self.stats.write_text(json.dumps(stats, ensure_ascii=False), encoding='utf-8')
        html_file = self.work / 'brief-full.html'
        result = self.run_cmd(ROOT / 'scripts' / 'render_poster.py', '--stats', self.stats, '--out', html_file)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        page = html_file.read_text(encoding='utf-8')
        self.assertIn('正面', page)
        self.assertIn('条 · 76.9%', page)

    def test_model_is_separated_from_tag_scope(self):
        profile = self.work / 'profile.json'
        with_model = self.run_cmd(ROOT / 'scripts' / 'profile.py', '--data', self.data,
                              '--query', 'NX8轮胎', '--out', profile)
        self.assertEqual(with_model.returncode, 0, with_model.stderr + with_model.stdout)
        result = json.loads(profile.read_text(encoding='utf-8'))
        self.assertEqual(result['target_model'], 'NX8')
        self.assertEqual(result['query_cleaned'], '轮胎')
        self.assertFalse(result['model_selection_required'])
        self.assertEqual(result['suggested']['main_scope']['key'], 'tag_any')
        self.assertEqual(result['suggested']['object_all_rows'], 2)

        nx8_scope = self.work / 'nx8-scope.json'
        nx8_scope.write_text(json.dumps({
            'data_file': str(self.data), 'topic': 'NX8轮胎', 'query_raw': 'NX8轮胎', 'period': '周',
            'target_model': 'NX8',
            'main_scope': {'key': 'tag_any', 'terms': ['轮胎'], 'phenomenon': ''},
        }, ensure_ascii=False), encoding='utf-8')
        scoped_stats = self.work / 'nx8-stats.json'
        scoped = self.run_cmd(ROOT / 'scripts' / 'analyze.py', '--scope', nx8_scope, '--out', scoped_stats)
        self.assertEqual(scoped.returncode, 0, scoped.stderr + scoped.stdout)
        self.assertEqual(json.loads(scoped_stats.read_text(encoding='utf-8'))['m2']['n'], 2)

        all_models = self.run_cmd(ROOT / 'scripts' / 'profile.py', '--data', self.data,
                              '--query', '轮胎', '--out', profile)
        self.assertEqual(all_models.returncode, 0, all_models.stderr + all_models.stdout)
        self.assertTrue(json.loads(profile.read_text(encoding='utf-8'))['model_selection_required'])

    def test_object_term_must_not_be_repeated_as_viewpoint_condition(self):
        """「哨兵模式」不得再被误加「且观点标签含哨兵」而漏数。"""
        data = self.work / 'sentinel.csv'
        headers = ['数据日期', '二级标签', '三级标签', '四级标签', '观点标签', '情感', '内容', '车型']
        rows = [
            ['2026-09-01', '智能驾驶', '辅助驾驶', '哨兵模式', '功能正常', '正面', '哨兵模式功能正常。', 'NX8'],
            ['2026-09-02', '智能驾驶', '辅助驾驶', '哨兵模式', '哨兵提醒', '中性', '询问哨兵提醒。', 'NX8'],
        ]
        with data.open('w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(rows)
        scope = self.work / 'sentinel-scope.json'
        scope.write_text(json.dumps({
            'data_file': str(data), 'topic': '哨兵模式', 'query_raw': '哨兵模式', 'period': '专项',
            'target_model': 'NX8',
            'main_scope': {'key': 'tag_any', 'terms': ['哨兵模式'], 'phenomenon': '哨兵'},
        }, ensure_ascii=False), encoding='utf-8')
        stats_file = self.work / 'sentinel-stats.json'
        result = self.run_cmd(ROOT / 'scripts' / 'analyze.py', '--scope', scope, '--out', stats_file)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        stats = json.loads(stats_file.read_text(encoding='utf-8'))
        self.assertEqual(stats['m2']['n'], 2)
        self.assertEqual(stats['meta']['scope_desc']['main'], '二/三/四级标签/观点标签含「哨兵模式」')

    def test_intent_normalizes_seat_words_before_scope_discovery(self):
        seat_data = self.work / 'seat.csv'
        headers = ['数据日期', '二级标签', '三级标签', '四级标签', '观点标签', '情感', '内容', '车型']
        with seat_data.open('w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerow(['2026-09-01', '智能座舱', '座椅系统', '座椅', '座椅异响', '负面', '座椅有异响。', 'NX8'])
        profile = self.work / 'seat-profile.json'
        for query, expected_confirmation in [('座椅声音', False), ('坐椅声音', False), ('坐位声音', True)]:
            result = self.run_cmd(ROOT / 'scripts' / 'profile.py', '--data', seat_data, '--query', query, '--out', profile)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            intent = json.loads(profile.read_text(encoding='utf-8'))['intent']
            self.assertEqual(intent['object_query_canonical'], '座椅')
            self.assertEqual(intent['requires_lexical_confirmation'], expected_confirmation)

    def test_viewpoint_label_is_in_main_keyword_scope(self):
        """关键词只存在观点标签时，也必须能发现并进入正式主口径。"""
        data = self.work / 'viewpoint-only.csv'
        headers = ['数据日期', '二级标签', '三级标签', '四级标签', '观点标签', '情感', '内容', '车型']
        rows = [
            ['2026-09-01', '车身外观', '车门系统', '外饰件', '车门把手松动', '负面', '门把手有松动。', 'NX8'],
            ['2026-09-02', '车身外观', '车门系统', '外饰件', '车门密封性好', '正面', '车门密封不错。', 'NX8'],
        ]
        with data.open('w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(rows)
        profile_file = self.work / 'viewpoint-profile.json'
        prof = self.run_cmd(ROOT / 'scripts' / 'profile.py', '--data', data,
                            '--query', '车门把手松动', '--out', profile_file)
        self.assertEqual(prof.returncode, 0, prof.stderr + prof.stdout)
        profile = json.loads(profile_file.read_text(encoding='utf-8'))
        self.assertEqual(profile['suggested']['object']['level'], '观点标签')
        self.assertEqual(profile['suggested']['object_all_rows'], 1)

        scope = self.work / 'viewpoint-scope.json'
        scope.write_text(json.dumps({
            'data_file': str(data), 'topic': '车门把手松动', 'query_raw': '车门把手松动', 'period': '专项',
            'target_model': 'NX8',
            'main_scope': {'key': 'tag_any', 'terms': ['车门把手松动'], 'phenomenon': ''},
        }, ensure_ascii=False), encoding='utf-8')
        stats_file = self.work / 'viewpoint-stats.json'
        analyzed = self.run_cmd(ROOT / 'scripts' / 'analyze.py', '--scope', scope, '--out', stats_file)
        self.assertEqual(analyzed.returncode, 0, analyzed.stderr + analyzed.stdout)
        self.assertEqual(json.loads(stats_file.read_text(encoding='utf-8'))['m2']['n'], 1)

    def test_spill_requires_keyword_and_separates_related_expansion(self):
        """无关服务声量不得因外溢关键词缺失而混入直命中。"""
        data = self.work / 'spill-gate.csv'
        headers = ['数据日期', '一级标签', '二级标签', '三级标签', '四级标签', '观点标签', '情感', '内容', '车型', '声音ID']
        rows = [
            ['2026-09-01', '产品品质', '整车品质', '车身外观', '车门把手', '门把手弹不开', '负面', '门把手弹不开。', 'NX8', 'main'],
            ['2026-09-02', '售后服务', '维修服务', '机电维修', '维修方案', '维修门把手', '负面', '门把手维修后仍收不回。', 'NX8', 'direct'],
            ['2026-09-03', '售后服务', '修后关怀', '补偿', '补偿催办', '尾灯补偿催到账', '负面', '尾灯更换后的补偿没有到账。', 'NX8', 'irrelevant'],
            ['2026-09-04', '售后服务', '维修服务', '机电维修', '维修方案', '不接受拆门板维修', '负面', '不接受拆门板维修。', 'NX8', 'related'],
        ]
        with data.open('w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(rows)
        scope = self.work / 'spill-gate-scope.json'
        scope.write_text(json.dumps({
            'data_file': str(data), 'topic': '门把手', 'query_raw': '门把手', 'period': '专项',
            'target_model': 'NX8', 'spill_keywords': ['门把手'], 'spill_related_terms': ['拆门板'],
            'main_scope': {'key': 'tag_any', 'terms': ['车门把手'], 'phenomenon': ''},
        }, ensure_ascii=False), encoding='utf-8')
        stats_file = self.work / 'spill-gate-stats.json'
        result = self.run_cmd(ROOT / 'scripts' / 'analyze.py', '--scope', scope, '--out', stats_file)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        stats = json.loads(stats_file.read_text(encoding='utf-8'))
        self.assertEqual(stats['m6']['spill_total'], 1)
        self.assertEqual(stats['m6']['service_total'], 1)
        self.assertEqual(stats['m6']['related_total'], 1)
        self.assertEqual(stats['m6']['contract']['direct_terms'], ['门把手'])
        direct = [x for x in stats['spill_detail'] if x['spill_class'] == '关键词直命中']
        self.assertEqual(len(direct), 1)
        self.assertEqual(direct[0]['matched_terms'], '门把手')
        self.assertNotIn('irrelevant', [x['source_ref'] for x in stats['spill_detail']])
        excel_file = self.work / 'spill-gate.xlsx'
        rendered = self.run_cmd(ROOT / 'scripts' / 'render_excel.py', '--stats', stats_file, '--out', excel_file)
        self.assertEqual(rendered.returncode, 0, rendered.stderr + rendered.stdout)
        self.assertTrue(excel_file.exists())

    def test_push_cli_and_identity_fallback_are_safe(self):
        sys.path.insert(0, str(ROOT / 'scripts'))
        import render_push
        cli_path = self.work / 'lark-cli'
        cli_path.write_text('', encoding='utf-8')
        with patch.dict(os.environ, {'LARK_CLI_PATH': ''}, clear=False), \
             patch.object(render_push.shutil, 'which', side_effect=lambda n: '/env/node/bin/lark-cli' if n == 'lark-cli' else None):
            self.assertEqual(render_push.find_cli(), '/env/node/bin/lark-cli')

        config = self.work / 'config.json'
        config.write_text(json.dumps({'apps': [{'users': [{'user_open_id': 'ou_alpha'}]}]}, ensure_ascii=False), encoding='utf-8')
        with patch.object(render_push, 'run_result', return_value={'output': 'not logged in', 'returncode': 6, 'timed_out': False}):
            target, err, source = render_push.resolve_target(str(cli_path), 'self', config)
        self.assertEqual((target, err, source), ('ou_alpha', None, 'config_fallback'))

        config.write_text(json.dumps({'userOpenId': 'ou_legacy'}, ensure_ascii=False), encoding='utf-8')
        self.assertEqual(render_push._read_config_user_open_id(config), ['ou_legacy'])
        config.write_text(json.dumps({'apps': [{'users': [{'user_open_id': 'ou_alpha'}, {'userOpenId': 'ou_beta'}]}]}, ensure_ascii=False), encoding='utf-8')
        with patch.object(render_push, 'run_result', return_value={'output': '', 'returncode': 6, 'timed_out': False}):
            target, err, source = render_push.resolve_target(str(cli_path), 'self', config)
        self.assertIsNone(target)
        self.assertIn('多个 user_open_id', err)
        self.assertIsNone(source)

    def test_weekly_trend_uses_date_range_not_week_number(self):
        sys.path.insert(0, str(ROOT / 'scripts'))
        import common
        self.assertEqual(common.period_label('2026-W27', 'week'), '06/29–07/05')
        self.assertEqual(common.period_label('2026-W53', 'week'), '2026/12/28–2027/01/03')

    def test_confirmed_date_window_limits_main_metrics_but_keeps_trend_reference(self):
        scope = self.work / 'window-scope.json'
        scope.write_text(json.dumps({
            'data_file': str(self.data), 'topic': '轮胎', 'query_raw': '轮胎', 'period': '周',
            'analysis_date_range': {'start': '2026-09-01', 'end': '2026-09-02', 'label': '测试区间'},
            'main_scope': {'key': 'l4', 'value': '轮胎', 'phenomenon': ''},
        }, ensure_ascii=False), encoding='utf-8')
        stats_file = self.work / 'window-stats.json'
        result = self.run_cmd(ROOT / 'scripts' / 'analyze.py', '--scope', scope, '--out', stats_file)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        stats = json.loads(stats_file.read_text(encoding='utf-8'))
        self.assertEqual(stats['m2']['n'], 2)
        self.assertEqual(stats['m2']['negative_n'], 0)
        self.assertEqual(stats['trace']['analysis_rows'], 2)
        self.assertEqual(stats['m5']['rows'][-1]['n'], 4)

    def test_incomplete_runtime_assets_fail_closed(self):
        staged = self.work / 'scratch'
        shutil.copytree(ROOT / 'scripts', staged / 'scripts')
        result = self.run_cmd(staged / 'scripts' / 'render_poster.py', '--verify-resources', cwd=staged)
        self.assertEqual(result.returncode, 2)
        self.assertIn('资源不完整', result.stderr)

    def test_runtime_stager_copies_complete_assets(self):
        staged = self.work / 'complete-runtime'
        result = self.run_cmd(ROOT / 'scripts' / 'stage_runtime.py', '--out', staged)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        verify = self.run_cmd(staged / 'scripts' / 'render_poster.py', '--verify-resources', cwd=staged)
        self.assertEqual(verify.returncode, 0, verify.stderr + verify.stdout)

    def test_unclassified_negative_voice_never_becomes_user_facing_other(self):
        seat_data = self.work / 'seat-shape.csv'
        headers = ['数据日期', '二级标签', '三级标签', '四级标签', '观点标签', '情感', '内容', '车型']
        rows = [
            ['2026-09-01', '智能座舱', '座椅系统', '座椅', '座椅舒适', '正面', '座椅很舒适。', 'NX8'],
            ['2026-09-02', '智能座舱', '座椅系统', '座椅', '座椅包裹性好', '正面', '座椅包裹性不错。', 'NX8'],
            ['2026-09-03', '智能座舱', '座椅系统', '座椅', '座椅偏硬', '负面', '座椅坐久了偏硬。', 'NX8'],
            ['2026-09-04', '智能座舱', '座椅系统', '座椅', '请问座椅如何调节', '中性', '请问座椅如何调节。', 'NX8'],
        ]
        with seat_data.open('w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(rows)
        scope = self.work / 'seat-shape-scope.json'
        scope.write_text(json.dumps({
            'data_file': str(seat_data), 'topic': '座椅', 'query_raw': '座椅', 'period': '周',
            'target_model': 'NX8',
            'main_scope': {'key': 'tag_any', 'terms': ['座椅'], 'phenomenon': ''},
        }, ensure_ascii=False), encoding='utf-8')
        stats_file = self.work / 'seat-shape-stats.json'
        result = self.run_cmd(ROOT / 'scripts' / 'analyze.py', '--scope', scope, '--out', stats_file)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        stats = json.loads(stats_file.read_text(encoding='utf-8'))
        self.assertEqual(stats['m4']['negative_n'], 1)
        self.assertEqual(stats['m4']['unclassified_n'], 1)
        self.assertEqual(stats['m4']['exclusive'], [])
        self.assertEqual(stats['m4']['shape_coverage'], 0)
        self.assertEqual(stats['m4']['themes']['正面']['total'], 2)
        self.assertEqual(stats['m4']['themes']['正面']['classified_n'], 2)
        self.assertEqual(stats['m4']['themes']['正面']['coverage'], 100.0)
        self.assertEqual(stats['m4']['themes']['中性']['total'], 1)
        self.assertEqual(stats['m4']['themes']['中性']['classified_n'], 1)
        self.assertEqual(stats['m4']['themes']['中性']['coverage'], 100.0)
        self.assertNotIn('问题高度同质', [x['kind'] for x in stats['m9']['insights']])
        html_file = self.work / 'seat-shape.html'
        rendered = self.run_cmd(ROOT / 'scripts' / 'render_poster.py', '--stats', stats_file, '--out', html_file)
        self.assertEqual(rendered.returncode, 0, rendered.stderr + rendered.stdout)
        page = html_file.read_text(encoding='utf-8')
        self.assertNotIn('其他', page)
        self.assertIn('本期不展示负面主题图', page)
        self.assertIn('规则覆盖 0%', page)
        self.assertIn('座椅偏硬(1)', page)


if __name__ == '__main__':
    suite = unittest.TestSuite([
        TestVocBriefRegression('test_data_lineage_store_name_and_quote_dedup'),
        TestVocBriefRegression('test_poster_has_theme_and_unique_quotes'),
        TestVocBriefRegression('test_full_mode_poster_uses_emotion_percentage_parameter'),
        TestVocBriefRegression('test_model_is_separated_from_tag_scope'),
        TestVocBriefRegression('test_object_term_must_not_be_repeated_as_viewpoint_condition'),
        TestVocBriefRegression('test_intent_normalizes_seat_words_before_scope_discovery'),
        TestVocBriefRegression('test_viewpoint_label_is_in_main_keyword_scope'),
        TestVocBriefRegression('test_spill_requires_keyword_and_separates_related_expansion'),
        TestVocBriefRegression('test_push_cli_and_identity_fallback_are_safe'),
        TestVocBriefRegression('test_weekly_trend_uses_date_range_not_week_number'),
        TestVocBriefRegression('test_confirmed_date_window_limits_main_metrics_but_keeps_trend_reference'),
        TestVocBriefRegression('test_incomplete_runtime_assets_fail_closed'),
        TestVocBriefRegression('test_runtime_stager_copies_complete_assets'),
        TestVocBriefRegression('test_unclassified_negative_voice_never_becomes_user_facing_other'),
    ])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not result.wasSuccessful())
