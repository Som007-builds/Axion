import os
import pandas as pd
from sklearn.model_selection import train_test_split


def split_dataset():
    input_path = os.path.join("eval", "Data", "labeled_pairs.csv")
    df = pd.read_csv(input_path)

    # 70% train, 30% temp (val + test)
    train_df, temp_df = train_test_split(
        df,
        test_size=0.30,
        random_state=42,
        stratify=df["label"]
    )

    # Split temp 50/50 into val and test (15% / 15% of total)
    val_df, test_df = train_test_split(
        temp_df,
        test_size=0.50,
        random_state=42,
        stratify=temp_df["label"]
    )

    train_path = os.path.join("eval", "Data", "train.csv")
    val_path = os.path.join("eval", "Data", "val.csv")
    test_path = os.path.join("eval", "Data", "test.csv")

    train_df.to_csv(train_path, index=False)
    val_df.to_csv(val_path, index=False)
    test_df.to_csv(test_path, index=False)

    print(f"Total pairs: {len(df)}")
    print("\nClass distribution in train.csv (70%, n={}):".format(len(train_df)))
    print(train_df["label"].value_counts().to_string())

    print("\nClass distribution in val.csv (15%, n={}):".format(len(val_df)))
    print(val_df["label"].value_counts().to_string())

    print("\nClass distribution in test.csv (15%, n={}):".format(len(test_df)))
    print(test_df["label"].value_counts().to_string())


if __name__ == "__main__":
    split_dataset()
