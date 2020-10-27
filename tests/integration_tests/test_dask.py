# -*- coding: utf-8 -*-
# Copyright (c) 2019 Uber Technologies, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
import os
import shutil
import tempfile

import dask.dataframe as dd
import pytest

from ludwig.api import LudwigModel
from ludwig.backend.dask import DaskBackend
from ludwig.utils.data_utils import read_parquet

from tests.integration_tests.utils import create_data_set_to_use, run_api_experiment
from tests.integration_tests.utils import audio_feature
from tests.integration_tests.utils import bag_feature
from tests.integration_tests.utils import binary_feature
from tests.integration_tests.utils import category_feature
from tests.integration_tests.utils import date_feature
from tests.integration_tests.utils import generate_data
from tests.integration_tests.utils import h3_feature
from tests.integration_tests.utils import image_feature
from tests.integration_tests.utils import numerical_feature
from tests.integration_tests.utils import sequence_feature
from tests.integration_tests.utils import set_feature
from tests.integration_tests.utils import text_feature
from tests.integration_tests.utils import timeseries_feature
from tests.integration_tests.utils import vector_feature


def train_with_backend(backend, dataset, config):
    model = LudwigModel(config, backend=backend)
    output_dir = None

    try:
        _, _, output_dir = model.train(
            dataset=dataset,
            skip_save_processed_input=True,
            skip_save_progress=True,
            skip_save_unprocessed_output=True
        )

        if isinstance(dataset, dd.DataFrame):
            # For now, prediction must be done on Pandas DataFrame
            dataset = dataset.compute()

        model.predict(dataset=dataset)
        return model.model.get_weights()
    finally:
        # Remove results/intermediate data saved to disk
        shutil.rmtree(output_dir, ignore_errors=True)


def run_api_experiment(input_features, output_features, data_parquet):
    config = {
        'input_features': input_features,
        'output_features': output_features,
        'combiner': {'type': 'concat', 'fc_size': 14},
        'training': {'epochs': 2}
    }

    dask_backend = DaskBackend()
    train_with_backend(dask_backend, data_parquet, config)

    # TODO: find guarantees on model parity
    # local_backend = LocalBackend()
    # dask_weights = train_with_backend(dask_backend, data_parquet, config)
    # local_weights = train_with_backend(local_backend, data_parquet, config)
    # for local_weight, dask_weight in zip(local_weights, dask_weights):
    #     np.testing.assert_allclose(local_weight, dask_weight, atol=1.e-2)

    data_df = read_parquet(data_parquet, df_lib=dask_backend.processor.df_lib)
    train_with_backend(dask_backend, data_df, config)


def run_test_parquet(input_features, output_features, num_examples=100):
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_filename = os.path.join(tmpdir, 'dataset.csv')
        dataset_csv = generate_data(input_features, output_features, csv_filename, num_examples=num_examples)
        dataset_parquet = create_data_set_to_use('parquet', dataset_csv)
        run_api_experiment(input_features, output_features, data_parquet=dataset_parquet)


def test_dask_tabular():
    # Single sequence input, single category output
    input_features = [
        sequence_feature(reduce_output='sum'),
        numerical_feature(normalization='zscore'),
        set_feature(),
        text_feature(),
        binary_feature(),
        bag_feature(),
        vector_feature(),
        h3_feature(),
        date_feature(),
    ]
    output_features = [category_feature(vocab_size=2, reduce_input='sum')]
    run_test_parquet(input_features, output_features)


def test_dask_timeseries():
    input_features = [timeseries_feature()]
    output_features = [numerical_feature()]
    run_test_parquet(input_features, output_features)


def test_dask_audio():
    with tempfile.TemporaryDirectory() as tmpdir:
        audio_dest_folder = os.path.join(tmpdir, 'generated_audio')
        input_features = [audio_feature(folder=audio_dest_folder)]
        output_features = [binary_feature()]
        run_test_parquet(input_features, output_features, num_examples=50)


def test_dask_lazy_load_audio_error():
    with tempfile.TemporaryDirectory() as tmpdir:
        audio_dest_folder = os.path.join(tmpdir, 'generated_audio')
        input_features = [
            audio_feature(
                folder=audio_dest_folder,
                preprocessing={
                    'in_memory': False,
                }
            )
        ]
        output_features = [binary_feature()]

        with pytest.raises(ValueError):
            run_test_parquet(input_features, output_features)


def test_dask_image():
    with tempfile.TemporaryDirectory() as tmpdir:
        image_dest_folder = os.path.join(tmpdir, 'generated_images')
        input_features = [
            image_feature(
                folder=image_dest_folder,
                encoder='resnet',
                preprocessing={
                    'in_memory': True,
                    'height': 12,
                    'width': 12,
                    'num_channels': 3,
                    'num_processes': 5
                },
                fc_size=16,
                num_filters=8
            ),
        ]
        output_features = [binary_feature()]
        run_test_parquet(input_features, output_features, num_examples=50)


def test_dask_lazy_load_image_error():
    with tempfile.TemporaryDirectory() as tmpdir:
        image_dest_folder = os.path.join(tmpdir, 'generated_images')
        input_features = [
            image_feature(
                folder=image_dest_folder,
                encoder='resnet',
                preprocessing={
                    'in_memory': False,
                    'height': 12,
                    'width': 12,
                    'num_channels': 3,
                    'num_processes': 5
                },
                fc_size=16,
                num_filters=8
            ),
        ]
        output_features = [binary_feature()]

        with pytest.raises(ValueError):
            run_test_parquet(input_features, output_features)