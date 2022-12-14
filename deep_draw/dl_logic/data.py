import numpy as np
import os
import glob
import yaml
import io
from tensorflow.python.lib.io import file_io
from yaml.loader import SafeLoader
from sklearn.model_selection import train_test_split
import tensorflow as tf
from deep_draw.dl_logic.params import batch_size, source_npy, storage_tfr, train_model_selection
from google.cloud import storage

def load_data_npy(test_size, max_items_per_class):
    if source_npy == 'local':
        root = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'raw_data','npy')
        print(root)
        all_files = glob.glob(os.path.join(root, '*.npy'))

        #initialize variables
        X = np.empty([0, 784])
        y = np.empty([0])
        class_names = []

        #load a subset of the data to memory
        for idx, file in enumerate(sorted(all_files)):
            data = np.load(file)
            print("\n✅ ", file, " loaded")
            data = data[0: max_items_per_class, :]
            labels = np.full(data.shape[0], idx)

            X = np.concatenate((X, data), axis=0)
            y = np.append(y, labels)

            class_name, ext = os.path.splitext(os.path.basename(file))
            class_names.append(class_name.replace("full_numpy_bitmap_", "").replace(".npy", ""))

    if source_npy == 'quickdraw':
        root = "gs://quickdraw_dataset/full/numpy_bitmap/"
        path_yaml= os.path.join(os.path.dirname(__file__),'categories.yaml')

        X = np.empty([0, 784])
        y = np.empty([0])

        with open(path_yaml) as f:
            class_names = yaml.load(f, Loader=SafeLoader)
            for idx, class_name in enumerate(class_names):
                f = io.BytesIO(file_io.read_file_to_string(root + f'{class_name}' + '.npy', binary_mode=True))
                data = np.load(f)
                print("\n✅ ", class_name, " loaded")
                data = data[0: max_items_per_class, :]
                labels = np.full(data.shape[0], idx)
                X = np.concatenate((X, data), axis=0)
                y = np.append(y, labels)

    data = None
    labels = None

    #shuffle (to be sure)
    permutation = np.random.permutation(y.shape[0])
    X = X[permutation, :]
    y = y[permutation]

    #separate into training and testing
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=test_size, shuffle=True)

    return X_train, X_test, y_train, y_test, class_names

def load_shard(root, shard, test_size=0.2, max_items_per_class= 5000):

    all_files = glob.glob(os.path.join(root, '*.npy'))

    #initialize variables
    X = np.empty([0, 784])
    y = np.empty([0])
    class_names = []

    #load a subset of the data to memory
    for idx, file in enumerate(sorted(all_files)):
        print(file)
        data = np.load(file)
        data = data[shard*max_items_per_class: (shard+1)*max_items_per_class, :]
        labels = np.full(data.shape[0], idx)

        X = np.concatenate((X, data), axis=0)
        y = np.append(y, labels)

        class_name, ext = os.path.splitext(os.path.basename(file))
        class_names.append(class_name.replace("full_numpy_bitmap_", "").replace(".npy", ""))

    data = None
    labels = None

    #shuffle (to be sure)
    permutation = np.random.permutation(y.shape[0])
    X = X[permutation, :]
    y = y[permutation]

    #separate into training and testing
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=test_size, shuffle=True)

    return X_train.astype(int), X_test.astype(int), y_train.astype(int), y_test.astype(int), class_names

def _bytes_feature(value):
    """Returns a bytes_list from a string / byte."""
    if isinstance(value, type(tf.constant(0))): # if value ist tensor
        value = value.numpy() # get value of tensor
    return tf.train.Feature(bytes_list=tf.train.BytesList(value=[value]))

def _float_feature(value):
    """Returns a floast_list from a float / double."""
    return tf.train.Feature(float_list=tf.train.FloatList(value=[value]))

def _int64_feature(value):
    """Returns an int64_list from a bool / enum / int / uint."""
    return tf.train.Feature(int64_list=tf.train.Int64List(value=[value]))

def serialize_array(array):
    array = tf.io.serialize_tensor(array)
    return array

def parse_single_image(image, label):

    #define the dictionary -- the structure -- of our single example
    data = {
        'height' : _int64_feature(image.shape[0]),
        'width' : _int64_feature(image.shape[1]),
        'depth' : _int64_feature(image.shape[2]),
        'raw_image' : _bytes_feature(serialize_array(image)),
        'label' : _int64_feature(label)
    }
    #create an Example, wrapping the single features
    out = tf.train.Example(features=tf.train.Features(feature=data))

    return out

def write_images_to_tfr_short(images, labels, filename:str="images"):
    filename= filename+".tfrecords"
    writer = tf.io.TFRecordWriter(filename) #create a writer that'll store our data to disk
    count = 0

    for index in range(len(images)):

        #get the data we want to write
        current_image = images[index]
        current_label = labels[index][0]

        out = parse_single_image(image=current_image, label=current_label)
        writer.write(out.SerializeToString())
        count += 1

    writer.close()
    print(f"Wrote {count} elements to TFRecord")
    return count

def parse_tfr_element(element):
    #use the same structure as above; it's kinda an outline of the structure we now want to create
    data = {
      'height': tf.io.FixedLenFeature([], tf.int64),
      'width':tf.io.FixedLenFeature([], tf.int64),
      'label':tf.io.FixedLenFeature([], tf.int64),
      'raw_image' : tf.io.FixedLenFeature([], tf.string),
      'depth':tf.io.FixedLenFeature([], tf.int64),
    }

    content = tf.io.parse_single_example(element, data)

    height = content['height']
    width = content['width']
    depth = content['depth']
    label = content['label']
    raw_image = content['raw_image']

    #get our 'feature'-- our image -- and reshape it appropriately
    feature = tf.io.parse_tensor(raw_image, out_type=tf.int64)
    feature = tf.reshape(feature, shape=[height,width,depth])
    return (feature, label)

def parse_tfexample_fn2(element):
    """Parse a single record which is expected to be a tensorflow.Example."""
    feature_to_type = {
        "ink": tf.io.FixedLenFeature([], dtype=tf.string),
        "height": tf.io.FixedLenFeature([], dtype=tf.int64),
        "width": tf.io.FixedLenFeature([], dtype=tf.int64),
        "class_index" : tf.io.FixedLenFeature([], dtype=tf.int64)
    }

    content = tf.io.parse_single_example(element, feature_to_type)
    height = content["height"]
    width = content["width"]
    label= content["class_index"]
    raw_image = content["ink"]
    feature = tf.io.parse_tensor(raw_image, out_type=tf.double)
    feature = tf.reshape(feature, shape=[height,width])

    return (feature, label)

def get_dataset_multi(tfr_dir: str = "/content/", pattern: str = "*.tfrecords"):
    files = glob.glob(os.path.join(tfr_dir, pattern), recursive=False)
    #print(files)

    #create the dataset
    dataset = tf.data.TFRecordDataset(files)

    #pass every single feature through our mapping function
    if train_model_selection == "cnn":
        dataset = dataset.map(parse_tfr_element)
    if train_model_selection == "rnn":
        dataset = dataset.map(parse_tfexample_fn2)

    return dataset

def get_dataset_multi_gcs(files):
    #create the dataset
    dataset = tf.data.TFRecordDataset(files)
    dataset = dataset.map(parse_tfr_element)
    return dataset

def load_tfrecords_dataset(source_type = 'train', batch_size=32):
    # Load dataset
    if storage_tfr == 'local':
        if train_model_selection == 'cnn':
            dataset = get_dataset_multi(tfr_dir='../../raw_data/tfrecords/', pattern=f"*_{source_type}.tfrecords")
            dataset = dataset.batch(batch_size)
            dataset = dataset.map(lambda x, y:(tf.cast(x, tf.float32)/255.0, y))
        if train_model_selection == 'rnn':
            dataset = get_dataset_multi(tfr_dir='../../raw_data/tfrecords/', pattern=f"*_{source_type}.tfrecords")
            dataset = dataset.batch(batch_size)

    if storage_tfr == 'gcs':
        client = storage.Client(project='deep-draw-project')
        bucket = client.bucket(bucket_name='tfrecords-files')
        records = [os.path.join('gs://tfrecords-files/', f.name) for f in
                 bucket.list_blobs()]
        data_records = [elem for elem in records if f"_{source_type}" in elem]
        data_records = ['gs://tfrecords-files/angel_train.tfrecords', 'gs://tfrecords-files/ant_train.tfrecords']
        dataset = get_dataset_multi_gcs(data_records)
        dataset = dataset.batch(batch_size)
        dataset = dataset.map(lambda x, y:(tf.cast(x, tf.float32)/255.0, y))

    print("\n✅ tfrecords", source_type, " loaded")
    return dataset


def create_tfrecords():
    for shard in range(10):
        print(shard)
        X_train, X_test, y_train, y_test, class_names = load_shard('../../raw_data/npy/', shard, test_size=0.3, max_items_per_class=10000)
        X_train = X_train.reshape(-1,28,28,1)
        X_test = X_test.reshape(-1,28,28,1)
        y_train = y_train.reshape(-1,1)
        y_test = y_test.reshape(-1,1)
        write_images_to_tfr_short(X_train, y_train, filename=f"../../raw_data/tfrecords/shard_{shard}_train")
        write_images_to_tfr_short(X_test, y_test, filename=f"../../raw_data/tfrecords/shard_{shard}_test")
