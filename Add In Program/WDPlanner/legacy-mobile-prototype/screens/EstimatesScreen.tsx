import React, { useEffect, useState } from 'react';
import { Alert, Button, FlatList, SafeAreaView, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { deleteEstimate, listEstimates, searchEstimates } from '../db/estimatesRepo';
import type { EstimateRow } from '../types/models';

export default function EstimatesScreen() {
  const [q, setQ] = useState('');
  const [items, setItems] = useState<EstimateRow[]>([]);

  const refresh = async () => {
    try {
      const data = q.trim() ? await searchEstimates(q.trim()) : await listEstimates();
      setItems(data);
    } catch (e) {
      Alert.alert('오류', String(e));
    }
  };

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onDelete = (id: number) => {
    Alert.alert('삭제', '해당 견적을 삭제할까요?', [
      { text: '취소', style: 'cancel' },
      {
        text: '삭제',
        style: 'destructive',
        onPress: async () => {
          try {
            await deleteEstimate(id);
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
      <Text style={{ fontSize: 20, fontWeight: '700', marginBottom: 12 }}>견적 목록</Text>

      <View style={{ flexDirection: 'row', gap: 8, marginBottom: 12 }}>
        <TextInput
          value={q}
          onChangeText={setQ}
          placeholder="고객명 검색"
          style={{ flex: 1, borderWidth: 1, borderColor: '#ddd', borderRadius: 8, padding: 10 }}
        />
        <Button title="검색" onPress={refresh} />
      </View>

      <FlatList
        data={items}
        keyExtractor={item => String(item.id)}
        renderItem={({ item }) => (
          <View style={{ borderWidth: 1, borderColor: '#eee', borderRadius: 10, padding: 12, marginBottom: 10 }}>
            <Text style={{ fontWeight: '800' }}>{item.customer_name}</Text>
            <Text style={{ color: '#666' }}>ID: {item.id}</Text>
            <Text style={{ color: '#666' }}>저장: {item.created_at}</Text>
            <View style={{ flexDirection: 'row', justifyContent: 'flex-end', marginTop: 8 }}>
              <TouchableOpacity onPress={() => onDelete(item.id)} style={{ paddingHorizontal: 12, paddingVertical: 8 }}>
                <Text style={{ color: '#d11' }}>삭제</Text>
              </TouchableOpacity>
            </View>
          </View>
        )}
        ListEmptyComponent={<Text style={{ color: '#888' }}>저장된 견적이 없습니다.</Text>}
      />
    </SafeAreaView>
  );
}


