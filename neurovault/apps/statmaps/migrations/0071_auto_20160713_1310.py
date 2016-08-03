# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
from neurovault.apps.statmaps.tasks import save_resampled_transformation_single
from neurovault.apps.statmaps.utils import is_search_compatible
from pybraincompare.mr.transformation import make_resampled_transformation_vector
import os
import nearpy
import numpy as np
import pickle
import nibabel as nib
#import redis

resample_dim = [4,4,4]

def change_resample_dim(apps, schema_editor):
    global resample_dim

    Image = apps.get_model("statmaps", "Image")
    count = Image.objects.count()
    for i, image in enumerate(Image.objects.all()):
        print "Fixing image %d (%d/%d)"%(image.pk, i+1, count)

        try:
            os.path.exists(str(image.reduced_representation.file))
            image.reduced_representation = save_resampled_transformation_single(image.pk, resample_dim)
            #os.remove(str(image.reduced_representation.file)) # TODO: remove old reduced_representation files
        except ValueError:
            print "This image needs no resampling due to not previous resampled transformation"


def build_engine(apps, schema_editor):
    ### Build Engine
    ## Main parameters
    n_bits = 7
    hash_counts = 40
    distance = nearpy.distances.EuclideanDistance()
    global resample_dim

    Image = apps.get_model("statmaps", "Image")

    # Get 100 features, for dimension selection and in case PCA is selected
    i = 0
    for image in Image.objects.all():
        try: #TODO: Look carefully if the image has to go into the engine or not
            os.path.exists(str(image.reduced_representation.file))

            nii_obj = nib.load(image.file.path)  # standard_mask=True is default
            feature = make_resampled_transformation_vector(nii_obj, resample_dim)

            if i == 0:
                features = np.empty([99,feature.shape[0]])
                features[i,:] = feature
                i += 1
            else:
                features[i, :] = feature
                i += 1
            if i == 99:
                break
        except ValueError:
            print "This image (%s) has no reduced representation" %image.pk

    #########
    # REDIS #
    #########
    # redis_object = redis.Redis(host='redis', port=6379, db=0)
    # redis_storage = nearpy.storage.RedisStorage(redis_object)
    # config = redis_storage.load_hash_configuration('neurovault')
    #if config is None:

    # Config is None: create hash from scratch, with 10 projections
    lshash = []
    ## Hash building
    # Random binary projections
    for k in xrange(hash_counts):
        nearpy_rbp = nearpy.hashes.RandomBinaryProjections('rbp_%d' % k, n_bits)
        lshash.append(nearpy_rbp)
        # PCA Binary projections
        # Get 100 dummy images to train the PCA space
        ## Apply:
        # for k in xrange(hash_counts):
        #     nearpy_rbp = nearpy.hashes.PCABinaryProjections('rbp_%d' % k, n_bits, features[:99, :].T)
        #     lshash.append(nearpy_rbp)

    # else:
    #     lshash = []
    #     for k in xrange(hash_counts):
    #         config = redis_storage.load_hash_configuration('rbp_%d' % k)
    #         # Config is existing, create hash with None parameters
    #         # Apply configuration loaded from redis
    #         lshash_aux = nearpy.hashes.RandomBinaryProjections(None, None)
    #         lshash_aux.apply_config(config)
    #         lshash.append(lshash_aux)
        # PCA Binary projections
        # Get 100 dummy images to train the PCA space
        ## Apply:
        # for k in xrange(hash_counts):
        #     nearpy_rbp = nearpy.hashes.PCABinaryProjections('rbp_%d' % k, n_bits, features[:99, :].T)
        #     lshash.append(nearpy_rbp)

    ## Filter
    filter_N = nearpy.filters.NearestFilter(100)

    ## Create Engine
    nearpy_engine = nearpy.Engine(features.shape[1], lshashes=lshash, distance=distance, vector_filters=[filter_N]) #storage=redis_storage

    ## Fill the Engine
    for image in Image.objects.all():
        try: #TODO: Look carefully if the image has to go into the engine or not
            os.path.exists(str(image.reduced_representation.file))
            if is_search_compatible(image.pk):
                feature = np.load(image.reduced_representation.file)
                print "Length:", len(feature.tolist()), "Image:", image.pk
                feature[np.isnan(feature)] = 0
                nearpy_engine.store_vector(feature.tolist(), image.pk)
            else:
                print "Image with PK %s has reduced representation but is not search compatible" % image.pk
        except ValueError:
            print "This image (%s) has no reduced representation" % image.pk

    pickle.dump(nearpy_engine,
                open('/code/neurovault/apps/statmaps/tests/nearpy_engine.p', "wb"))


class Migration(migrations.Migration):

    dependencies = [
        ('statmaps', '0070_auto_20160526_2216'),
    ]

    operations = [
         migrations.RunPython(build_engine),
         migrations.RunPython(change_resample_dim),
         # migrations.DeleteModel('Similarity'),
         # migrations.DeleteModel('Comparison')
    ]
