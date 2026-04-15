import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Button, FlatList, SafeAreaView, Text, TextInput, View } from 'react-native';
import { listProducts } from '../db/repositories';
import { saveEstimate } from '../db/estimatesRepo';
import type { Product } from '../types/models';
import { calculateAll, type BaseComponentInput, type SelectedOptionInput } from '../core/calc';

export default function CalculatorScreen() {
  const [products, setProducts] = useState<Product[]>([]);
  const [customerName, setCustomerName] = useState('');
  const [baseComponents, setBaseComponents] = useState<BaseComponentInput[]>([
    { mode: 'select', widthMm: 0, productId: null, additionalFees: [] },
  ]);
  const [options, setOptions] = useState<SelectedOptionInput[]>([]);

  useEffect(() => {
    listProducts().then(setProducts).catch(err => Alert.alert('오류', String(err)));
  }, []);

  const result = useMemo(() => {
    return calculateAll({ products, baseComponents, options });
  }, [products, baseComponents, options]);

  const addBaseRow = () => {
    setBaseComponents(prev => [...prev, { mode: 'select', widthMm: 0, productId: null, additionalFees: [] }]);
  };

  const onSave = async () => {
    if (!customerName.trim()) {
      Alert.alert('확인', '고객명을 입력해주세요.');
      return;
    }
    const estimate_data = {
      baseComponents,
      options,
      basePrice: result.basePrice,
      additionalPrice: result.additionalPrice,
      totalPrice: result.totalPrice,
      detail: result.detail,
    };
    try {
      await saveEstimate({ customer_name: customerName.trim(), estimate_data });
      Alert.alert('완료', '견적이 저장되었습니다.');
    } catch (e) {
      Alert.alert('오류', String(e));
    }
  };

  return (
    <SafeAreaView style={{ flex: 1, padding: 16 }}>
      <Text style={{ fontSize: 20, fontWeight: '700', marginBottom: 12 }}>가구 견적 계산기(오프라인)</Text>

      <Text style={{ fontWeight: '600' }}>고객명</Text>
      <TextInput
        value={customerName}
        onChangeText={setCustomerName}
        placeholder="고객명을 입력하세요"
        style={{ borderWidth: 1, borderColor: '#ddd', borderRadius: 8, padding: 10, marginBottom: 12 }}
      />

      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <Text style={{ fontWeight: '700' }}>기본 구성</Text>
        <Button title="기본 구성 추가" onPress={addBaseRow} />
      </View>

      <FlatList
        data={baseComponents}
        keyExtractor={(_, idx) => String(idx)}
        renderItem={({ item, index }) => (
          <View style={{ borderWidth: 1, borderColor: '#eee', borderRadius: 10, padding: 12, marginBottom: 10 }}>
            <Text style={{ fontWeight: '700', marginBottom: 6 }}>구성 {index + 1}</Text>

            <Text style={{ color: '#666' }}>제품 ID (설정 화면에서 제품 리스트 확인)</Text>
            <TextInput
              keyboardType="numeric"
              value={item.productId ? String(item.productId) : ''}
              onChangeText={t =>
                setBaseComponents(prev => {
                  const next = [...prev];
                  next[index] = { ...next[index], productId: t ? Number(t) : null };
                  return next;
                })
              }
              placeholder="예: 5"
              style={{ borderWidth: 1, borderColor: '#ddd', borderRadius: 8, padding: 10, marginBottom: 8 }}
            />

            <Text style={{ color: '#666' }}>가로(mm)</Text>
            <TextInput
              keyboardType="numeric"
              value={item.widthMm ? String(item.widthMm) : ''}
              onChangeText={t =>
                setBaseComponents(prev => {
                  const next = [...prev];
                  next[index] = { ...next[index], widthMm: t ? Number(t) : 0 };
                  return next;
                })
              }
              placeholder="예: 3300"
              style={{ borderWidth: 1, borderColor: '#ddd', borderRadius: 8, padding: 10 }}
            />
          </View>
        )}
      />

      <View style={{ paddingVertical: 12 }}>
        <Text style={{ fontWeight: '700' }}>합계</Text>
        <Text>기본: {Math.round(result.basePrice).toLocaleString('ko-KR')}원</Text>
        <Text>추가옵션: {Math.round(result.additionalPrice).toLocaleString('ko-KR')}원</Text>
        <Text style={{ fontSize: 18, fontWeight: '800' }}>
          총액: {Math.round(result.totalPrice).toLocaleString('ko-KR')}원
        </Text>
      </View>

      <Button title="견적 저장" onPress={onSave} />

      <View style={{ marginTop: 12 }}>
        <Text style={{ color: '#888', fontSize: 12 }}>
          주의: 현재는 1차 골격 버전이라 “제품 선택 UI/추가옵션/추가금/비고”는 다음 단계에서 완성합니다.
        </Text>
      </View>
    </SafeAreaView>
  );
}


