import React, { useEffect, useState } from 'react';
import { Alert, Button, FlatList, SafeAreaView, Text, TextInput, View } from 'react-native';
import { deleteProduct, getNextId, listProducts, upsertProduct } from '../db/repositories';
import type { PricingType, Product } from '../types/models';

export default function SettingsScreen() {
  const [items, setItems] = useState<Product[]>([]);
  const [name, setName] = useState('');
  const [pricingType, setPricingType] = useState<PricingType>('30cm');
  const [price30, setPrice30] = useState('');
  const [price1, setPrice1] = useState('');
  const [price1m, setPrice1m] = useState('');

  const refresh = async () => {
    try {
      setItems(await listProducts());
    } catch (e) {
      Alert.alert('오류', String(e));
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const addProduct = async () => {
    if (!name.trim()) {
      Alert.alert('확인', '제품명을 입력해주세요.');
      return;
    }
    try {
      const id = await getNextId('products');
      const p: Product = {
        id,
        name: name.trim(),
        pricing_type: pricingType,
        price_30cm: pricingType === '30cm' ? Number(price30 || 0) : undefined,
        price_1cm: pricingType === '30cm' ? Number(price1 || 0) : undefined,
        price_1m: pricingType === '1m' ? Number(price1m || 0) : undefined,
      };
      await upsertProduct(p);
      setName('');
      setPrice30('');
      setPrice1('');
      setPrice1m('');
      await refresh();
    } catch (e) {
      Alert.alert('오류', String(e));
    }
  };

  const removeProduct = async (id: number) => {
    Alert.alert('삭제', `제품(ID:${id})을 삭제할까요?`, [
      { text: '취소', style: 'cancel' },
      {
        text: '삭제',
        style: 'destructive',
        onPress: async () => {
          try {
            await deleteProduct(id);
            await refresh();
          } catch (e) {
            Alert.alert('오류', String(e));
          }
        },
      },
    ]);
  };

  return (
    <SafeAreaView style={{ flex: 1, padding: 16 }}>
      <Text style={{ fontSize: 20, fontWeight: '700', marginBottom: 12 }}>설정(편집 가능)</Text>

      <Text style={{ fontWeight: '700', marginBottom: 6 }}>제품 추가(간단)</Text>
      <TextInput
        value={name}
        onChangeText={setName}
        placeholder="제품명"
        style={{ borderWidth: 1, borderColor: '#ddd', borderRadius: 8, padding: 10, marginBottom: 8 }}
      />
      <TextInput
        value={pricingType}
        onChangeText={t => setPricingType((t === '1m' ? '1m' : '30cm') as PricingType)}
        placeholder="pricing_type: 30cm 또는 1m"
        style={{ borderWidth: 1, borderColor: '#ddd', borderRadius: 8, padding: 10, marginBottom: 8 }}
      />
      {pricingType === '30cm' ? (
        <View style={{ gap: 8, marginBottom: 8 }}>
          <TextInput
            value={price30}
            onChangeText={setPrice30}
            keyboardType="numeric"
            placeholder="price_30cm"
            style={{ borderWidth: 1, borderColor: '#ddd', borderRadius: 8, padding: 10 }}
          />
          <TextInput
            value={price1}
            onChangeText={setPrice1}
            keyboardType="numeric"
            placeholder="price_1cm"
            style={{ borderWidth: 1, borderColor: '#ddd', borderRadius: 8, padding: 10 }}
          />
        </View>
      ) : (
        <TextInput
          value={price1m}
          onChangeText={setPrice1m}
          keyboardType="numeric"
          placeholder="price_1m"
          style={{ borderWidth: 1, borderColor: '#ddd', borderRadius: 8, padding: 10, marginBottom: 8 }}
        />
      )}
      <Button title="제품 저장(추가)" onPress={addProduct} />

      <View style={{ height: 16 }} />

      <Text style={{ fontWeight: '800', marginBottom: 8 }}>제품 목록</Text>
      <FlatList
        data={items}
        keyExtractor={item => String(item.id)}
        renderItem={({ item }) => (
          <View style={{ borderWidth: 1, borderColor: '#eee', borderRadius: 10, padding: 12, marginBottom: 10 }}>
            <Text style={{ fontWeight: '800' }}>
              {item.id}. {item.name}
            </Text>
            <Text style={{ color: '#666' }}>
              {item.pricing_type === '1m'
                ? `1m: ${item.price_1m ?? 0}`
                : `30cm: ${item.price_30cm ?? 0}, 1cm: ${item.price_1cm ?? 0}`}
            </Text>
            <View style={{ flexDirection: 'row', justifyContent: 'flex-end', marginTop: 6 }}>
              <Button title="삭제" color="#d11" onPress={() => removeProduct(item.id)} />
            </View>
          </View>
        )}
        ListEmptyComponent={<Text style={{ color: '#888' }}>제품이 없습니다.</Text>}
      />

      <Text style={{ color: '#888', fontSize: 12, marginTop: 8 }}>
        다음 단계: 추가옵션/비고 카테고리 CRUD UI도 동일 패턴으로 확장합니다.
      </Text>
    </SafeAreaView>
  );
}


